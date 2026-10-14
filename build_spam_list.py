"""Builds the spam list the app downloads, from the US FTC's public "Do Not Call reported calls" data.

Source: https://www.ftc.gov/developer/api/v0/endpoints/do-not-call-dnc-reported-calls-data-api
The data is consumer-reported and, in the FTC's words, "not verified" - a number is on this list
because people complained about it, nothing more.

Output: one line per number, `NNNNNNNNNN,reports`, most reported first, after a `#` header line.
Host the file anywhere the app can GET it and put that address in SpamListStore.LIST_URL.

    python build_spam_list.py --days 14 --out spam_list.csv

The API needs an api.data.gov key (free: https://api.data.gov/signup/). Pass it in the
DATA_GOV_API_KEY environment variable; without one the shared DEMO_KEY is used, which is limited to
a few dozen requests and so only yields a small sample.
"""
import argparse
import collections
import datetime
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


def fetch(params, key):
    query = urllib.parse.urlencode({**params, 'api_key': key, 'items_per_page': PAGE})
    request = urllib.request.Request(API + '?' + query, headers={'User-Agent': 'spam-list-builder'})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--days', type=int, default=14, help='how many days of complaints to count')
    parser.add_argument('--out', default='spam_list.csv')
    parser.add_argument('--max-pages', type=int, default=0, help='stop after this many requests (0 = no limit)')
    args = parser.parse_args()

    key = os.environ.get('DATA_GOV_API_KEY') or 'DEMO_KEY'
    today = datetime.date.today()
    start = today - datetime.timedelta(days=args.days)
    window = {'created_date_from': '"%s"' % start.isoformat(), 'created_date_to': '"%s"' % today.isoformat()}

    counts = collections.Counter()
    offset = pages = rows = 0
    while True:
        try:
            page = fetch({**window, 'offset': offset}, key)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                print('rate limit reached after %d requests - writing what was fetched' % pages, file=sys.stderr)
                break
            raise
        records = page.get('data') or []
        pages += 1
        for record in records:
            rows += 1
            digits = re.sub(r'\D', '', str(record.get('attributes', {}).get('company-phone-number') or ''))
            if len(digits) == 11 and digits.startswith('1'):
                digits = digits[1:]
            # US numbers only; the feed also carries blanks and the odd malformed row.
            if len(digits) == 10 and digits[0] not in '01':
                counts[digits] += 1
        if len(records) < PAGE or (args.max_pages and pages >= args.max_pages):
            break
        offset += PAGE
        time.sleep(0.2)

    with open(args.out, 'w', encoding='utf-8', newline='\n') as out:
        out.write('# source=FTC DNC reported calls; from=%s; to=%s; complaints=%d; numbers=%d\n'
                  % (start.isoformat(), today.isoformat(), rows, len(counts)))
        for number, reports in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            out.write('%s,%d\n' % (number, reports))
    print('%d requests, %d complaints, %d numbers -> %s' % (pages, rows, len(counts), args.out))


if __name__ == '__main__':
    main()
