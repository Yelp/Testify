from collections import defaultdict
import sqlalchemy as SA
import time

from testify.plugins.sql_reporter import Tests, Builds, TestResults, make_engine

def add_command_line_options(parser):
    parser.add_option("--rearrange-tests-branch", action="append", dest="rearrange_tests_branches", type="string", help="Rearrange test cases by run time. Look at this branch in the reporting database for test run times")
    parser.add_option("--rearrange-tests-runs-since", action="store", dest="rearrange_tests_runs_since", type="int", help="Rearrange test cases by run time, but only look at runs that ended fewer than this many seconds ago when calculating run times. May be combined with --rearrange-tests-branch. If --rearrange-tests-branch is specified, this defaults to 86400 (1 day)")
    parser.add_option("--rearrange-tests-db-config", action="store", dest="rearrange_tests_db_config", type="string", default=None, help="Path to a yaml file describing the SQL database to report into.")
    parser.add_option('--rearrange-tests-db-url', action="store", dest="rearrange_tests_db_url", type="string", default=None, help="The URL of a SQL database to report into.")



def rearrange_discovered_tests(options, test_cases):
    if not options.rearrange_tests_branches or options.rearrange_tests_runs_since:
        return test_cases

    if not (options.rearrange_tests_db_config or options.rearrange_tests_db_url):
        raise ValueError("A database URL or config must be specified when rearranging test cases by run time.")


    engine = make_engine(
        db_url=options.rearrange_tests_db_url,
        db_config=options.rearrange_tests_db_config,
    )
    conn = engine.connect()

    whereclauses = []

    # Only calculate stats for the tests we're rearranging.
    whereclauses.append(SA.tuple_(
        Tests.c.module,
        Tests.c.class_name,
    ).in_([(tc.__module__, tc.__class__.__name__) for tc in test_cases]))

    if options.rearrange_tests_branches:
        whereclauses.append(Builds.c.branch.in_(options.rearrange_tests_branches))

    whereclauses.append(Builds.c.end_time > (options.rearrange_tests_runs_since or (time.time() - 24 * 60 * 60)))

    # For each test case, calculate the average of the sum of the run times of each test.
    subquery = SA.subquery(
        'averages',
        columns=[
            Tests.c.module,
            Tests.c.class_name,
            Tests.c.method_name,
            SA.func.sum(TestResults.c.run_time).label('sum_run_time'),
        ],
        whereclause=SA.and_(*whereclauses),
        group_by=[Tests.c.module, Tests.c.class_name, Tests.c.method_name],
        from_obj=Builds.join(TestResults, TestResults.c.build == Builds.c.id).join(Tests, TestResults.c.test == Tests.c.id),
    )

    query = SA.select(
        columns=[
            'module',
            'class_name',
            SA.func.avg(subquery.c.sum_run_time).label('avg_sum_run_time'),
        ],
        from_obj=subquery,
        group_by=['module', 'class_name']
    )

    results = conn.execute(query)

    # If we don't know the run time (because we haven't seen it before), assume it's infinity so it'll run first.
    times_by_test_case = defaultdict(lambda: float('Infinity'))
    for result in results:
        times_by_test_case[(result.module, result.class_name)] = result['avg_sum_run_time']

    test_cases = sorted(
        test_cases,
        key=(lambda tc: times_by_test_case[(tc.__module__, tc.__class__.__name__)]),
        reverse=True,
    )

    return test_cases
