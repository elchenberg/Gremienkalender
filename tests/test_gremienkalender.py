import unittest

import lxml

import gremienkalender


class TestGremienkalender(unittest.TestCase):
    def test_get_allriscontainer(self):
        gremienkalender.REQUEST_DELAY = 0
        try:
            URL = 'https://www.berlin.de/ba-lichtenberg/politik-und-verwaltung/bezirksverordnetenversammlung/online/si018.asp'
            result = gremienkalender.get_allriscontainer(URL)
            self.assertIsInstance(result, lxml.html.HtmlElement)
            self.assertIs(type(result), lxml.html.HtmlElement)
            self.assertEqual(result.get('id'), 'allriscontainer')
        except Exception as exception:
            self.fail("Should not raise exceptions: {0}".format(
                type(exception)))


if __name__ == '__main__':
    unittest.main()
