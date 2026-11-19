# Publish the News Desk with the first DDA report export

The 09:46 report already includes Part 6 News Desk calls, but the detached DDA
report bridge previously exported only Top 2. Intelligent Capital consequently
had to wait for the later morning CSV record commit to display the news calls.

The report bridge now includes a whitelist of those same frozen news calls,
their original source fields, model and rule version. It does not rerun research,
change the email, change the schedule or wait for another publication task.
Headline controls, other sessions, outcome scores and private fields are absent.
A malformed optional calls payload is marked unavailable without blocking the
original report export. Existing first-write publication remains immutable.

Tests in `tests/test_dda_news_publication.py` cover the first 09:46 export,
private/outcome field exclusion, original-report preservation, timing guards,
duplicate hook retries, session/arm isolation and malformed optional data.
