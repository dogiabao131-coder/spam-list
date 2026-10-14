"""Builds the spam list the app downloads, from the US FTC's public "Do Not Call reported calls" data.

Source: https://www.ftc.gov/developer/api/v0/endpoints/do-not-call-dnc-reported-calls-data-api
The data is consumer-reported and, in the FTC's words, "not verified" - a number is on this list
because people complained about it, nothing more.

Two steps, so a daily run only asks the API for a few days instead of the whole window:

    # 1. fetch complaints per day into days/YYYY-MM-DD.csv (re-fetching a day replaces its file)
    python build_spam_list.py fetch --days 3
    # 2. add up the day files of the last N days into the list the app downloads
    python build_spam_list.py build --days 14 --out spam_list.csv

The list has one line per number, `NNNNNNNNNN,reports`, most reported first, after a `#` header.

The API needs an api.data.gov key (free: https://api.data.gov/signup/) in DATA_GOV_API_KEY; without
one the shared DEMO_KEY is used. The FTC backend also refuses bursts (HTTP 429) regardless of the
key, so requests are paced and a 429 is waited out.
"""
import argparse
import collections
import datetime
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.ftc.gov/v0/dnc-complaints'
PAGE = 50  # the API's maximum
PAUSE = 2.5  # seconds between requests; faster than this draws 429s
DAYS_DIR = 'days'


def fetch_page(params, key):
    query = urllib.parse.urlencode({**params, 'api_key': key, 'items_per_page': PAGE})
    request = urllib.request.Request(API + '?' + query, headers={'User-Agent': 'spam-list-builder'})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            wait = int(error.headers.get('Retry-After') or 0) or 60 * (attempt + 1)
            print('  429 - waiting %ds' % wait, file=sys.stderr)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            # The API is slow at times; a timed-out page is simply asked for again.
            print('  %s - retrying in 30s' % error, file=sys.stderr)
            time.sleep(30)
    raise RuntimeError('API still failing after several retries')


def us_number(raw):
    digits = re.sub(r'\D', '', str(raw or ''))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    # US numbers only; the feed also carries blanks and the odd malformed row.
    return digits if len(digits) == 10 and digits[0] not in '01' else None


def fetch_day(day, key):
    """Counts of complaints per number for complaints created on [day]."""
    counts = collections.Counter()
    offset = rows = 0
    while True:
        page = fetch_page({'created_date': '"%s"' % day.isoformat(), 'offset': offset}, key)
        records = page.get('data') or []
        for record in records:
            rows += 1
            number = us_number(record.get('attributes', {}).get('company-phone-number'))
            if number:
                counts[number] += 1
        if len(records) < PAGE:
            return counts, rows
        offset += PAGE
        time.sleep(PAUSE)


def cmd_fetch(args):
    key = os.environ.get('DATA_GOV_API_KEY') or 'DEMO_KEY'
    os.makedirs(DAYS_DIR, exist_ok=True)
    today = datetime.date.today()
    for back in range(args.days):
        day = today - datetime.timedelta(days=back)
        counts, rows = fetch_day(day, key)
        path = os.path.join(DAYS_DIR, day.isoformat() + '.csv')
        # A day the FTC has not published yet comes back empty; keep whatever was there before.
        if rows == 0 and os.path.exists(path):
            print('%s: nothing returned, keeping %s' % (day, path))
            continue
        with open(path, 'w', encoding='utf-8', newline='\n') as out:
            out.write('# complaints=%d\n' % rows)
            for number, reports in sorted(counts.items()):
                out.write('%s,%d\n' % (number, reports))
        print('%s: %d complaints, %d numbers' % (day, rows, len(counts)))
        time.sleep(PAUSE)


def cmd_build(args):
    today = datetime.date.today()
    first = today - datetime.timedelta(days=args.days - 1)
    counts = collections.Counter()
    complaints = days = 0
    for path in sorted(glob.glob(os.path.join(DAYS_DIR, '*.csv'))):
        try:
            day = datetime.date.fromisoformat(os.path.basename(path)[:-4])
        except ValueError:
            continue
        if not first <= day <= today:
            continue
        days += 1
        with open(path, encoding='utf-8') as src:
            for line in src:
                if line.startswith('# complaints='):
                    complaints += int(line.split('=')[1])
                elif line.strip() and not line.startswith('#'):
                    number, reports = line.strip().split(',')
                    counts[number] += int(reports)
    with open(args.out, 'w', encoding='utf-8', newline='\n') as out:
        out.write('# source=FTC DNC reported calls; from=%s; to=%s; days=%d; complaints=%d; numbers=%d\n'
                  % (first.isoformat(), today.isoformat(), days, complaints, len(counts)))
        for number, reports in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            out.write('%s,%d\n' % (number, reports))
    print('%d day files, %d complaints, %d numbers -> %s' % (days, complaints, len(counts), args.out))
    # Old day files are no longer needed once they leave the window.
    for path in glob.glob(os.path.join(DAYS_DIR, '*.csv')):
        try:
            if datetime.date.fromisoformat(os.path.basename(path)[:-4]) < first - datetime.timedelta(days=7):
                os.remove(path)
        except ValueError:
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    fetch = sub.add_parser('fetch', help='fetch the last N days of complaints into days/')
    fetch.add_argument('--days', type=int, default=3)
    build = sub.add_parser('build', help='add up the last N days into the list')
    build.add_argument('--days', type=int, default=14)
    build.add_argument('--out', default='spam_list.csv')
    args = parser.parse_args()
    {'fetch': cmd_fetch, 'build': cmd_build}[args.command](args)


if __name__ == '__main__':
    main()
