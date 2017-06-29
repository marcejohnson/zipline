"""
Module for building a complete dataset from local directory with csv files.
"""
import os
import sys

import logbook
import numpy
import pandas
import pytz

from zipline.utils.calendars import register_calendar_alias
from zipline.utils.cli import maybe_show_progress

logger = logbook.Logger(__name__)

def csvdir_equities(tframe='daily', start=None, end=None):
    """
    Generate an ingest function for custom data bundle

    Parameters
    ----------
    tframe: string, optional
        The data time frame ('minute', 'daily')
    start : datetime, optional
        The start date to query for. By default this pulls the full history
        for the calendar.
    end : datetime, optional        
        The end date to query for. By default this pulls the full history
        for the calendar.
    Returns
    -------
    ingest : callable
        The bundle ingest function for the given set of symbols.
    Examples
    --------
    This code should be added to ~/.zipline/extension.py
    .. code-block:: python
       from zipline.data.bundles import csvdir, register
       register('csvdir', csvdir.csvdir_equities(sys.environ['CSVDIR'], 'minute'))

    Notes
    -----
    Environment variable CSVDIR must contain path to the directory with <symbol>.csv files
    sids for each symbol will be the index into the symbols sequence.
    """

    def ingest(environ, asset_db_writer, minute_bar_writer, daily_bar_writer,
               adjustment_writer, calendar, start_session, end_session, cache,
               show_progress, output_dir, start=start, end=end):

        csvdir = os.environ.get('CSVDIR')
        if not csvdir:
            logger.error("CSVDIR environment variable is not set")
            sys.exit(1)
        if not os.path.isdir(csvdir):
            logger.error("%s is not a directory" % csvdir)
            sys.exit(1)

        symbols = sorted(item.split('.csv')[0] for item in os.listdir(csvdir) if item.endswith('.csv'))

        if not symbols:
            logger.error("no <symbol>.csv files found in %s" % csvdir)

        metadata = pandas.DataFrame(numpy.empty(len(symbols),
                    dtype=[('start_date', 'datetime64[ns]'),
                           ('end_date', 'datetime64[ns]'),
                           ('auto_close_date', 'datetime64[ns]'),
                           ('symbol', 'object')]))

        def _pricing_iter():
            with maybe_show_progress(symbols, show_progress,
                                     label='Loading custom pricing data: ') as it:
                for sid, symbol in enumerate(it):                    
                    logger.debug('%s: sid %s' % (symbol, sid))

                    try:
                        df = pandas.read_csv(os.path.join(csvdir, '%s.csv' % symbol),
                            parse_dates=[0], infer_datetime_format=True, index_col=0).sort_index()
                    except:
                        logger.error("unable to parse %s.csv" % symbol)
                        continue

                    # skip empty
                    if not len(df.index):
                        continue

                    # the start date is the date of the first trade and
                    # the end date is the date of the last trade
                    start_date = df.index[0]
                    end_date = df.index[-1]

                    # The auto_close date is the day after the last trade.
                    ac_date = end_date + pandas.Timedelta(days=1)
                    metadata.iloc[sid] = start_date, end_date, ac_date, symbol

                    # Fix na and Fill missing dates
                    sessions = calendar.sessions_in_range(start_date, end_date)
                    df = df.reindex(
                        sessions.tz_localize(None),
                        copy=False,
                    ).fillna(0.0)

                    yield sid, df

        writer = minute_bar_writer if tframe == 'minute' else daily_bar_writer
        writer.write(_pricing_iter(), show_progress=show_progress)

        # drop metadata rows that are empty
        metadata = metadata.dropna()

        # Hardcode the exchange to "CSVDIR" for all assets and (elsewhere)
        # register "CSVDIR" to resolve to the NYSE calendar, because these are
        # all equities and thus can use the NYSE calendar.
        metadata['exchange'] = "CSVDIR"
        asset_db_writer.write(equities=metadata)

        adjustment_writer.write(splits=None, dividends=None)

    return ingest

register_calendar_alias("CSVDIR", "NYSE")
