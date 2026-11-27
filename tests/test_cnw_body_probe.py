"""Day-156d: the CNW body probe asks politely and stops on refusal (no network here)."""
import cnw_body_probe as P

BODY = '<section class="release-body container">' + '<p>Issuer text. </p>' * 40 + '</section>'


def test_a_served_page_is_read_and_measured_against_the_editions_floor():
    out = P.probe(['https://www.newswire.ca/news-releases/a-1.html'], get=lambda u: (200, BODY), pause=0)
    page = out['pages'][0]
    assert page['body_found'] and page['meets_min_body'] and page['opening'].startswith('Issuer text.')
    assert out['verdict'] == 'ISSUER_TEXT_AVAILABLE'


def test_it_stops_after_two_refusals_and_never_retries():
    seen = []

    def refused(url):
        seen.append(url)
        return 403, '<html>Please complete the challenge</html>'
    out = P.probe([f'https://www.newswire.ca/news-releases/x-{i}.html' for i in range(5)], get=refused, pause=0)
    assert len(seen) == 2 and out['asked'] == 2 and out['verdict'] == 'REFUSED_OR_NO_TEXT'
    assert out['pages'][0]['challenged'] and out['pages'][-1]['skipped'].startswith('stopped after 2')


def test_the_sample_leads_with_cu_to():
    urls = P.sample(5)
    assert urls[0] == P.CU_RELEASE and len(urls) <= 5
