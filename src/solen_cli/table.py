import logging
import numbers
from datetime import datetime
from collections import OrderedDict

from prettytable import PrettyTable

logger = logging.getLogger(__name__)


def generate(cols, data, defaults=None, labels=None, align="c"):
    """
    Return a new PrettyTable instance representing the list.

    Arguments:

        cols - An iterable of strings that specify what
               are the columns of the table.

               for example: ['id','name']

        data - An iterable of dictionaries, each dictionary must
               have key's corresponding to the cols items.

               for example: [{'id':'123', 'name':'Pete']

        defaults - A dictionary specifying default values for
                   key's that don't exist in the data itself.

                   for example: {'deploymentId':'123'} will set the
                   deploymentId value for all rows to '123'.

        labels - A dictionary mapping a column name to a label that
                 will be used for the table header

    """

    defaults = defaults or {}
    labels = labels or {}

    def get_values_per_column(column, row_data):
        if column in row_data:
            if row_data[column] and isinstance(row_data[column], str):
                row_data[column] = get_timestamp(row_data[column]) or row_data[column]
            elif row_data[column] and isinstance(row_data[column], list):
                row_data[column] = ",".join(row_data[column])
            elif isinstance(row_data[column], bool):
                pass  # Taking care of False (otherwise would be changed to '')
            elif isinstance(row_data[column], numbers.Number):
                pass  # Taking care of 0 and 0.0 (otherwise would be changed to '')
            elif not row_data[column]:
                # if it's empty list, don't print []
                row_data[column] = ""
            return row_data[column]
        return defaults.get(column, "")

    pt = PrettyTable([labels.get(col, col) for col in cols])

    for item in data:
        values_row = []
        for column in cols:
            values_row.append(get_values_per_column(column, item))
        pt.add_row(values_row)

    pt.align = align
    return pt


def print_dicts(data, sort=None):
    pt = dicts_to_pt(data, sort)
    print(pt)
    return True


def dicts_to_html(data, sort=None):
    pt = dicts_to_pt(data, sort)
    return pt.get_html_string(format=True)


def dict_to_pt(data, sort=None, align="c"):
    table_data = []
    for key, value in data.items():
        table_data.append(dict(key=key, value=value))
    return dicts_to_pt(table_data, sort=sort, align=align)


def dicts_to_pt(data, sort=None, align="c"):
    if not data:
        logger.info("missing data")
        return False
    all_keys = sum([list(x.keys()) for x in data], [])  # get a list of all keys
    columns = list(OrderedDict.fromkeys(all_keys))  # remove duplicates, uses OrderedDict to keep the order of columns
    return get_data_table(columns, data, sortby=sort, align=align)


def get_data_table(
    columns, items, max_width=None, defaults=None, sortby=None, labels=None, line_numbers=True, align="c"
):
    if items is None:
        items = []
    elif not isinstance(items, list):
        items = [items]

    if line_numbers:
        if "#" in columns:
            columns.remove("#")
        columns.insert(0, "#")
        line_number = 1
        for item in items:
            item["#"] = line_number
            line_number += 1

    pt = generate(columns, data=items, defaults=defaults, labels=labels, align=align)
    if max_width:
        pt.max_width = max_width
    pt.sortby = sortby
    pt.reversesort = False
    return pt


def get_timestamp(data):
    try:
        datetime.strptime(data[:10], "%Y-%m-%d")
        return data.replace("T", " ").replace("Z", " ")
    except ValueError:
        # not a timestamp
        return None
