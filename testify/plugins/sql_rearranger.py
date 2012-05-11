import sqlalchemy as SA
import time

from testify.plugins.sql_reporter import Tests, Fixtures, Builds, TestResults, FixtureResults, make_engine


def add_command_line_options(parser):
    parser.add_option("--rearrange-tests-branch", action="append", dest="rearrange_tests_branches", type="string", help="Rearrange test cases by run time. Look at this branch in the reporting database for test run times")
    parser.add_option("--rearrange-tests-buildname", action="store", dest="rearrange_tests_buildname", type="string", help="Rearrange test cases by run time. Look only at builds matching this pattern.")
    parser.add_option("--rearrange-tests-runs-since", action="store", dest="rearrange_tests_runs_since", type="int", help="Rearrange test cases by run time, but only look at runs that ended fewer than this many seconds ago when calculating run times. May be combined with --rearrange-tests-branch. If --rearrange-tests-branch is specified, this defaults to 86400 (1 day)")
    parser.add_option("--rearrange-tests-db-config", action="store", dest="rearrange_tests_db_config", type="string", default=None, help="Path to a yaml file describing the SQL database to report into.")
    parser.add_option('--rearrange-tests-db-url', action="store", dest="rearrange_tests_db_url", type="string", default=None, help="The URL of a SQL database to report into.")


def rearrange_discovered_tests(options, test_cases):
    if not (options.rearrange_tests_branches or options.rearrange_tests_runs_since or options.rearrange_tests_buildname):
        return test_cases

    if not (options.rearrange_tests_db_config or options.rearrange_tests_db_url):
        raise ValueError("A database URL or config must be specified when rearranging test cases by run time.")

    engine = make_engine(
        db_url=options.rearrange_tests_db_url,
        db_config=options.rearrange_tests_db_config,
    )
    conn = engine.connect()

    # First, figure out which builds we'll be looking at for timing data.
    whereclauses = []
    if options.rearrange_tests_branches:
        whereclauses.append(Builds.c.branch.in_(options.rearrange_tests_branches))

    if options.rearrange_tests_buildname:
        whereclauses.append(Builds.c.buildname.like(options.rearrange_tests_buildname))

    whereclauses.append(Builds.c.end_time > (options.rearrange_tests_runs_since or (time.time() - 24 * 60 * 60)))

    builds = [row['id'] for row in conn.execute(SA.select(
        columns=[
            Builds.c.id,
        ],
        whereclause=SA.and_(*whereclauses)
    ))]

    # For each test case, calculate the average of the sum of the run times of each test.
    subquery_test = SA.subquery(
        'sums_test',
        columns=[
            Tests.c.module,
            Tests.c.class_name,
            SA.func.sum(TestResults.c.run_time).label('sum_run_time'),
        ],
        whereclause=TestResults.c.build.in_(builds),
        group_by=[Tests.c.module, Tests.c.class_name, TestResults.c.build],
        from_obj=TestResults.join(Tests, TestResults.c.test == Tests.c.id),
    )

    subquery_fixture = SA.subquery(
        'sums_fixture',
        columns=[
            Fixtures.c.module,
            Fixtures.c.class_name,
            SA.func.sum(FixtureResults.c.run_time).label('sum_run_time'),
        ],
        whereclause=SA.and_(FixtureResults.c.build.in_(builds)),
        group_by=[Fixtures.c.module, Fixtures.c.class_name, FixtureResults.c.build],
        from_obj=FixtureResults.join(Fixtures, FixtureResults.c.fixture == Fixtures.c.id),
    )

    query_test = SA.select(
        columns=[
            'module',
            'class_name',
            SA.func.avg(subquery_test.c.sum_run_time).label('avg_sum_run_time'),
        ],
        from_obj=subquery_test,
        group_by=['module', 'class_name']
    )

    query_fixture = SA.select(
        columns=[
            'module',
            'class_name',
            SA.func.avg(subquery_fixture.c.sum_run_time).label('avg_sum_run_time'),
        ],
        from_obj=subquery_fixture,
        group_by=['module', 'class_name']
    )

    results_fixture = list(conn.execute(query_fixture))
    results_test = list(conn.execute(query_test))

    times_by_test_case = {}
    for result in list(results_test) + list(results_fixture):
        times_by_test_case.setdefault((result.module, result.class_name), 0)
        times_by_test_case[(result.module, result.class_name)] += result['avg_sum_run_time']

    # If we don't know the run time (because we haven't seen it before), assume it's Infinity so it'll run first.
    test_cases = sorted(
        test_cases,
        key=(lambda tc: times_by_test_case.get((tc.__module__, tc.__class__.__name__), float('Infinity'))),
        reverse=True,
    )

    return test_cases
