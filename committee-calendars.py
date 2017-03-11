# !/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.client
import time
import zlib

import lxml.html

BOROUGH_NAMES = ['Mitte', 'Friedrichshain-Kreuzberg', 'Pankow',
                 'Charlottenburg-Wilmersdorf', 'Spandau',
                 'Steglitz-Zehlendorf', 'Tempelhof-Schöneberg',
                 'Neukölln', 'Treptow-Köpenick', 'Marzahn-Hellersdorf',
                 'Lichtenberg', 'Reinickendorf']
BOROUGH_SLUGS = [b.lower().replace('ö', 'oe') for b in BOROUGH_NAMES]
BOROUGH_ID_DICT = dict(zip(BOROUGH_SLUGS, range(1,13)))

class Calendar():
    def __init__(self):
        self.events = []

    def add_event(self, event):
        self.events.append(event)

    def ics(self):
        if not self.events:
            return None
        ics = []
        ics.append('BEGIN:VCALENDAR')
        ics.append('VERSION:2.0')
        ics.append('PRODID:https://elchenberg.me')
        ics.append('X-WR-CALNAME:BVV %s: %s' % (self.borough,
                                                self.committee))
        ics.append('BEGIN:VTIMEZONE')
        ics.append('TZID:Europe/Berlin')
        ics.append('BEGIN:DAYLIGHT')
        ics.append('TZOFFSETFROM:+0100')
        ics.append('TZOFFSETTO:+0200')
        ics.append('TZNAME:CEST')
        ics.append('DTSTART:19700329T020000')
        ics.append('RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=-1SU;BYMONTH=3')
        ics.append('END:DAYLIGHT')
        ics.append('BEGIN:STANDARD')
        ics.append('TZOFFSETFROM:+0200')
        ics.append('TZOFFSETTO:+0100')
        ics.append('TZNAME:CET')
        ics.append('DTSTART:19701025T030000')
        ics.append('RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=-1SU;BYMONTH=10')
        ics.append('END:STANDARD')
        ics.append('END:VTIMEZONE')
        for event in self.events:
            ics.append(event.ics())
        ics.append('END:VCALENDAR')
        return '\r\n'.join(ics)

class Event():
    def __init__(self):
        self.url = None

    def ics(self):
        ics = []
        ics.append('BEGIN:VEVENT')
        ics.append('UID:%s' % self.uid)
        ics.append('DTSTAMP:%s' % self.dtstamp)
        ics.append('DTSTART;TZID=Europe/Berlin:%s' % self.dtstart)
        if self.duration:
            ics.append('DURATION:%s' % self.duration)
        else:
            ics.append('DURATION:PT2H')
        ics.append('SUMMARY:%s' % self.summary)
        if self.url:
            ics.append('DESCRIPTION:%s\\n%s' % (self.description, self.url))
            ics.append('URL:%s' % self.url)
        else:
            ics.append('DESCRIPTION:%s' % self.description)
        ics.append('END:VEVENT')
        return '\r\n'.join(ics)

request_wait = 3
session = http.client.HTTPSConnection('www.berlin.de', timeout=6)
request_time = time.time()

def get_response_text(url):
    global request_time

    elapsed_time = time.time() - request_time
    if elapsed_time < request_wait:
        time.sleep(request_wait - elapsed_time)

    session.request('GET', url, headers={'Accept-Encoding': 'gzip'})
    print('GET', url)
    response = session.getresponse()
    request_time = time.time()

    # assert response.status == 200
    # assert response.getheader('Content-Encoding') == 'gzip'

    gzip_data = response.read()

    # Tested decompression using different window size and buffer size values.
    # The only working window size values are 31 and 47 so I am going for 47
    # because it is in the range where the logarithm 'automatically accepts
    # either the zlib or gzip format'.
    # As for buffer size it seems to be best to go with the default value.
    # https://docs.python.org/3/library/zlib.html#zlib.decompress
    raw_data = zlib.decompress(gzip_data, 47)

    try:
        response_text = raw_data.decode('latin-1', 'strict')
    except UnicodeDecodeError:
        response_text = raw_data.decode('windows-1252', 'strict')
    return response_text

def get_date_query():
    today = time.localtime()
    year, month = today[0:2]
    template = 'YYV=%s&MMV=%s&YYB=%s&MMB=%s'
    date_query = template % (year, month, year, month + 1)
    if month > 12:
        date_query = template % (year, month, year + 1, 1)
    return date_query

def is_borough_id(obj):
    try:
        obj = int(obj)
        if not 1 <= obj <= 12:
            raise ValueError()
        return True
    except ValueError:
        return False

def get_borough_id(obj):
    if is_borough_id(obj):
        return int(obj)
    string = str(obj)
    string = string.lower()
    string = string.replace('ö', 'oe')
    error_message = 'No known/valid borough found in \'%s\'.' % str(obj)
    try:
        return BOROUGH_ID_DICT[string]
    except KeyError:
        # More lines of code but also
        # more readable than a next() statement:
        for borough in BOROUGH_ID_DICT:
            if borough in string:
                return BOROUGH_ID_DICT[borough]
        raise ValueError(error_message)

def get_borough_name(obj):
    if is_borough_id(obj):
        return BOROUGH_NAMES[int(obj)-1]
    else:
        return BOROUGH_NAMES[get_borough_id(obj)-1]

def get_borough_slug(obj):
    if is_borough_id(obj):
        return BOROUGH_SLUGS[int(obj)-1]
    else:
        return BOROUGH_SLUGS[get_borough_id(obj)-1]

html_template = ('<!DOCTYPE html>\n<html lang="de">\n<head>\n'+
                 '<meta charset="UTF-8">\n<meta name="viewport" '+
                 'content="width=device-width, initial-scale=1.0">\n'+
                 '<title>%s</title>\n<link rel="stylesheet" '+
                 'type="text/css" href="style.css">\n</head>\n<body>\n'+
                 '<header>\n<h1>%s</h1>\n<p>%s</p>\n</header>\n%s'+
                 '</body>\n</html>')
sect_template = '<section>\n<h2>%s</h2>\n<ul>\n%s</ul>\n</section>\n'
item_template = '<li><a href="%s">%s</a></li>\n'

def main():
    with open('input.txt', 'r') as textfile:
        borough_urls = [line.strip() for line in textfile.readlines()]

    boroughs = []
    for borough_url in borough_urls:
        response_text = get_response_text(borough_url)
        html_parser = lxml.html.fromstring(response_text)
        # html_parser.make_links_absolute(url)

        committee_ids = set()
        committee_list = html_parser.cssselect('#GRA')[0]
        for element in committee_list:
            text_inactive = 'inaktiv' in element.text_content()
            class_inactive = element.get('class') == 'calWeek'
            if text_inactive or class_inactive:
                continue
            committee_id = int(element.get('value'))
            committee_ids.add(committee_id)

        if not committee_ids:
            continue

        boroughs.append({
            'slug': get_borough_slug(borough_url),
            'name': get_borough_name(borough_url),
            'id': get_borough_id(borough_url),
            'url': borough_url,
            'committees': sorted(committee_ids)
        })

    html_data = {}
    date_query = get_date_query()
    for borough in boroughs:
        b_name = borough['name']
        b_slug = borough['slug']
        b_id = borough['id']
        b_url = borough['url']

        html_data[b_name] = []

        for c_id in borough['committees']:
            c_url = '%s?GRA=%s' % (b_url, c_id)

            url = '%s&%s' % (c_url, date_query)
            response_text = get_response_text(url)
            html_parser = lxml.html.fromstring(response_text)
            html_parser.make_links_absolute(c_url)

            calendar_rows = html_parser.cssselect('.zl12')
            calendar_rows += html_parser.cssselect('.zl11')
            if not calendar_rows:
                continue

            c_name = html_parser.cssselect('.tl1')[0][0].text_content()
            c_name = c_name.split('Sitzungen des Gremiums ')[1]
            c_name = c_name.split(' im Zeitraum')[0]

            calendar = Calendar()
            calendar.borough = b_name
            calendar.committee = c_name
            calendar.url = c_url
            for row in calendar_rows:
                event_date = row[0].text_content().strip()
                event_time = row[1].text_content().strip()
                if not (event_date and event_time):
                    continue
                datetime = '%s %s' % (event_date[4:], event_time[:5])
                datetime = time.strptime(datetime, '%d.%m.%Y %H:%M')

                event = Event()
                event.summary = '%s: %s' % (b_name, c_name)
                event.description = row[3].text_content().strip()
                if len(row[3]):
                    event.url = row[3][0].get('href')

                event.dtstart = time.strftime('%Y%m%dT%H%M%S', datetime)
                event.duration = 'PT2H'

                now_utc = time.localtime()
                event.dtstamp = time.strftime('%Y%m%dT%H%M%SZ', now_utc)

                uid_domain = '%03d.%s.berlin.de' % (c_id, b_slug)
                uid_local = event.dtstart
                event.uid = '%s@%s' % (uid_local, uid_domain)

                calendar.add_event(event)

            if calendar.ics():
                filename_template = '%s-%03d.ics'
                filename = filename_template % (b_slug, c_id)
                with open(filename, 'w') as f:
                    f.write(calendar.ics())
                html_data[b_name].append([filename, c_name])

    page_title = ('Gremienkalender der Berliner '+
                  'Bezirksverordnetenversammlungen')
    page_help = ('iCalendar-Dateien (.ics) zum Herunterladen oder '+
                 'Abonnieren')
    html_sections = ''
    for borough in sorted(html_data):
        items = html_data[borough]
        items = ''.join([item_template % (a, t) for a, t in items])
        section = sect_template % (borough, items)
        html_sections += section
    html_string = html_template % (page_title, page_title,
                                   page_help, html_sections)
    with open('index.html', 'w') as f:
        f.write(html_string)

if __name__ == '__main__':
    main()
