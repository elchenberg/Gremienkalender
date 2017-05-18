# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crawl and parse calendars of the Berlin Councils' committees.

Crawl and parse calendars of the Berlin Councils' committees and
convert forthcoming committee meetings to iCalendar data format and
write them to one iCalendar file per committee.
"""

import http.client
import os
import ssl
import time
import zlib

import lxml.html

HOST = 'www.berlin.de'
SESSION = http.client.HTTPSConnection(HOST, context=ssl.create_default_context(), timeout=10)
# With a delay greater than 4 seconds the server closes the connection between requests.
REQUEST_DELAY = 4
REQUEST_HEADERS = {'Connection': 'keep-alive', 'Accept-Encoding': 'gzip'}
DTSTAMP = '{}{:02d}{:02d}T{:02d}{:02d}{:02d}Z'.format(*time.gmtime())
BOROUGH_NAMES = {
    'ba-charlottenburg-wilmersdorf': 'Charlottenburg-Wilmersdorf',
    'ba-friedrichshain-kreuzberg': 'Friedrichshain-Kreuzberg',
    'ba-lichtenberg': 'Lichtenberg',
    'ba-marzahn-hellersdorf': 'Marzahn-Hellersdorf',
    'ba-mitte': 'Mitte',
    'ba-neukoelln': 'Neukölln',
    'ba-pankow': 'Pankow',
    'ba-reinickendorf': 'Reinickendorf',
    'ba-spandau': 'Spandau',
    'ba-steglitz-zehlendorf': 'Steglitz-Zehlendorf',
    'ba-tempelhof-schoeneberg': 'Tempelhof-Schöneberg',
    'ba-treptow-koepenick': 'Treptow-Köpenick'
}

def save_cookie(response):
    """Find and save ALLRIS session cookies from server response if present."""
    session_cookie = response.getheader('Set-Cookie')
    if session_cookie:
        session_cookie = session_cookie.split(';', 1)[0]
        REQUEST_HEADERS['Cookie'] = session_cookie

def decode_response(response_body):
    """Decode response body and return a unicode string."""
    try:
        response_body = response_body.decode('iso-8859-1', 'strict')
    except UnicodeDecodeError:
        print('decoding iso-8859-1 failed')
        try:
            response_body = response_body.decode('iso-8859-15', 'strict')
        except UnicodeDecodeError:
            print('decoding iso-8859-15 failed, too')
            response_body = response_body.decode('windows-1252', 'replace')
    return response_body

def find_allriscontainer(response_body, base_url):
    """Find allriscontainer div element in html page source string."""
    response_body = response_body.split('s-->', 1)[1]
    response_body = response_body.split('<!-- H', 1)[0]
    html = lxml.html.fromstring(response_body, base_url=base_url)
    for div in html.getiterator('div'):
        if div.get('id') and div.get('id') == 'allriscontainer':
            return div

def get_allriscontainer(url):
    """Return the *url*s' response body as an lxml.html.HtmlElement."""
    request_path = url.split('www.berlin.de', 1)[1]
    time.sleep(REQUEST_DELAY)
    SESSION.request('GET', request_path, headers=REQUEST_HEADERS)
    try:
        response = SESSION.getresponse()
    except http.client.BadStatusLine:
        # In Python <3.5 we need to re-connect when the remote end has closed the connection.
        print('Re-connecting to the server ...')
        SESSION.close()
        SESSION.request('GET', request_path, headers=REQUEST_HEADERS)
        response = SESSION.getresponse()
    response_body = response.read()
    if response.status == 200:
        save_cookie(response)
        response_body = zlib.decompress(response_body, 47)
        response_body = decode_response(response_body)
        return find_allriscontainer(response_body, url)

def findall_calendars(allriscontainer):
    """Return a list of calendar links extracted from html content."""
    for select in allriscontainer.getiterator('select'):
        if select.get('id') and select.get('id') == 'GRA':
            values = set()
            for option in select.getiterator('option'):
                if not option.get('class') == 'calWeek':
                    if not 'inaktiv' in option.text:
                        value = option.get('value')
                        value = int(value)
                        values.add(value)
            base = allriscontainer.base_url
            values = sorted(values)
            return ['{}?GRA={}'.format(base, value) for value in values]

def date_range(months=3):
    """Return an URL query string."""
    year_from, month_from, *_ = time.localtime()
    year_to = year_from
    month_to = month_from + months
    while month_to > 12:
        year_to += 1
        month_to -= 12
    template = 'YYV={}&MMV={}&YYB={}&MMB={}'
    return template.format(year_from, month_from, year_to, month_to)
DATE_RANGE = date_range()

def find_borough_slug(url):
    slug = url.split('/', 4)[3]
    slug = slug[3:]
    return slug

def find_committee_id(url):
    query_pairs = url.split('?', 1)[1]
    query_pairs = query_pairs.split('&')
    for pair in query_pairs:
        name, value = pair.split('=', 1)
        if name == 'GRA' and value.isdigit():
            return int(value)

def find_calendar_url(url):
    calendar_url = url
    calendar_url = calendar_url.split('&', 1)[0]
    return calendar_url

def find_calendar_uid(url):
    borough = find_borough_slug(url)
    committee = find_committee_id(url)
    calendar_uid = borough + '-' + '%03d' % committee
    calendar_uid = '%s-%03d' % (borough, committee)
    calendar_uid = '{}-{:03d}'.format(borough, committee)
    return calendar_uid

def find_calendar_borough(url):
    calendar_borough = url
    calendar_borough = calendar_borough.split('/', 4)[3]
    calendar_borough = BOROUGH_NAMES[calendar_borough]
    return calendar_borough

def find_calendar_committee(allriscontainer):
    cells = allriscontainer.getiterator('th')
    for cell in cells:
        if cell.get('colspan') == '6':
            committee = cell.text_content()
            committee = committee[23:].split(' im Zeitraum', 1)[0]
            return committee

def findall_tablerows_zl1n(allriscontainer):
    for table in allriscontainer.getiterator('table'):
        if table.get('class') == 'tl1':
            tablerows = []
            for row in table.getiterator('tr'):
                if row.get('class') == 'zl11' or row.get('class') == 'zl12':
                    tablerows.append(row)
            return tablerows

def find_event_dtstart(row):
    date_text = row[0].text[4:]
    time_text = row[1].text[:5]
    if date_text.strip() and time_text.strip():
        dtstart = (
            int(date_text[6:10]),
            int(date_text[3:5]),
            int(date_text[0:2]),
            int(time_text[0:2]),
            int(time_text[3:5]),
            0,
            0,
            0,
            0
        )
        elapsed_time = (time.time() - time.mktime(dtstart))
        one_day = 60*60*24
        if elapsed_time < 1*one_day:
            dtstart = '{}{:02d}{:02d}T{:02d}{:02d}{:02d}'.format(*dtstart)
            return dtstart

def find_event_description(row):
    try:
        return row[3][0].text
    except IndexError:
        return row[3].text

def find_event_url(row):
    try:
        href = row[3][0].get('href')
        return 'https://{}{}'.format(HOST, href)
    except IndexError:
        return ''

def findall_events(allriscontainer):
    events = []
    base_url = allriscontainer.base_url
    calendar_uid = find_calendar_uid(base_url)
    committee_name = find_calendar_committee(allriscontainer)
    rows = findall_tablerows_zl1n(allriscontainer)
    for row in rows:
        event = {
            'dtstamp': DTSTAMP,
            'dtstart': find_event_dtstart(row),
            'summary': find_calendar_borough(base_url) + ': ' + committee_name,
            'location': ''
        }
        if event.get('dtstart'):
            event['url'] = find_event_url(row)
            event['description'] = '{}\\n{}\\n-- \\nQuelle: {}\\nStand: {}'.format(
                find_event_description(row),
                event['url'],
                base_url,
                "{2:02d}.{1:02d}.{0}, {3:02d}:{4:02d} Uhr".format(
                    *time.localtime()
                )
            )
            event['uid'] = '{}-{}'.format(calendar_uid, event['dtstart'])
            #if event['url']:
                #event_page = get_allriscontainer(event['url'])
            #    pass
            events.append(event)
    return events

def extract_vcalendar(allriscontainer):
    """Return a list of committee meetings extracted from html content."""
    vcalendar = {
        'vevents': findall_events(allriscontainer),
    }
    if vcalendar.get('vevents'):
        base_url = allriscontainer.base_url
        vcalendar['url'] = find_calendar_url(base_url)
        vcalendar['uid'] = find_calendar_uid(base_url)
        vcalendar['borough'] = find_calendar_borough(base_url)
        vcalendar['committee'] = find_calendar_committee(allriscontainer)
        vcalendar['name'] = '{}: {}'.format(
            vcalendar['borough'],
            vcalendar['committee']
        )
        return vcalendar

def fold_content_lines(content):
    """Fold lines of *content* string to a length of 75 octets.

    "Lines of text SHOULD NOT be longer than 75 octets, excluding the line
    break.  Long content lines SHOULD be split into a multiple line
    representations using a line "folding" technique.  That is, a long
    line can be split between any two characters by inserting a CRLF
    immediately followed by a single linear white-space character"
    https://tools.ietf.org/html/rfc5545#section-3.1
    """
    content_lines = content.splitlines()
    folded_content_lines = []
    max_octets = 75
    for line in content_lines:
        while line:
            characters = max_octets
            encoded_line = line[:characters].encode('utf-8')
            while len(encoded_line) > max_octets:
                characters -= 1
                encoded_line = line[:characters].encode('utf-8')
            folded_content_lines.append(line[:characters])
            line = line[characters:]
            if line:
                line = ' '+line
    folded_content = '\n'.join(folded_content_lines)
    return folded_content+'\n'

def write_vcalendar_file(vcalendar):
    """Create iCalendar data format strings and write them to files."""
    if vcalendar.get('vevents'):
        with open(os.path.join('templates', 'vevent.ics'), 'r') as icsfile:
            vevent_template = icsfile.read()
        with open(os.path.join('templates', 'vcalendar.ics'), 'r') as icsfile:
            vcalendar_template = icsfile.read()
        vevents_string = ''
        for vevent in vcalendar['vevents']:
            vevent_string = vevent_template.format(**vevent)
            vevents_string += vevent_string
        vcalendar['vevents'] = vevents_string+'\n'
        vcalendar_string = vcalendar_template.format(**vcalendar)
        vcalendar_string = fold_content_lines(vcalendar_string)
        filename = '{}.ics'.format(vcalendar['uid'])
        filename = os.path.join('calendars', filename)
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w', newline='\r\n') as icsfile:
            icsfile.write(vcalendar_string)

def main():
    """The main function."""
    with open('links.txt', 'r') as txtfile:
        council_links = txtfile.read()
        council_links = council_links.splitlines()
        valid_links = {'http://www.berlin.de/ba-',
                       'https://www.berlin.de/ba'}
        council_links = [l for l in council_links if l[:24] in valid_links]

    for link in council_links:
        allriscontainer = get_allriscontainer(link)
        committee_links = findall_calendars(allriscontainer)
        for link in committee_links:
            link += '&' + DATE_RANGE
            allriscontainer = get_allriscontainer(link)
            vcalendar = extract_vcalendar(allriscontainer)
            if vcalendar:
                write_vcalendar_file(vcalendar)
    SESSION.close()

if __name__ == '__main__':
    main()
