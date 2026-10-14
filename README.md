# spam-list

A list of US phone numbers that consumers reported to the FTC as unwanted calls, rebuilt every day.

- **File:** [`spam_list.csv`](spam_list.csv) — one line per number, `NNNNNNNNNN,reports`, most reported
  first. The first line is a `#` comment with the date range and totals.
- **Source:** the US Federal Trade Commission's public
  [Do Not Call reported calls data](https://www.ftc.gov/policy-notices/open-government/data-sets/do-not-call-data).
  The FTC states that none of the reported information is verified: a number is here because people
  complained about it, nothing more. Numbers can be spoofed or reported by mistake.
- **Window:** complaints created in the last 14 days.
- **Update:** the `Update spam list` workflow runs `build_spam_list.py` daily and commits the result.
  It needs a free [api.data.gov](https://api.data.gov/signup/) key stored as the repository secret
  `DATA_GOV_API_KEY`.

Raw file for apps:
`https://raw.githubusercontent.com/dogiabao131-coder/spam-list/main/spam_list.csv`
