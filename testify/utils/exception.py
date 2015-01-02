"""Helper methods for formatting and manipulating tracebacks"""
import traceback


def format_exception_info(exception_info_tuple, formatter=None):
    if formatter is None:
        formatter = traceback.format_exception

    exctype, value, tb = exception_info_tuple
    # Skip test runner traceback levels
    while tb and is_relevant_tb_level(tb):
        tb = tb.tb_next
    if exctype is AssertionError:
        # Skip testify.assertions traceback levels
        length = count_relevant_tb_levels(tb)
        return formatter(exctype, value, tb, length)

    if not tb:
        return "Exception: %r (%r)" % (exctype, value)

    return formatter(exctype, value, tb)


def is_relevant_tb_level(tb):
    return '__testify' in tb.tb_frame.f_globals


def count_relevant_tb_levels(tb):
    length = 0
    while tb and not is_relevant_tb_level(tb):
        length += 1
        tb = tb.tb_next
    return length
