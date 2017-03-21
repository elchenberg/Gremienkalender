# !/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crawl and parse calendars of the Berlin Councils' committees.

Crawl and parse calendars of the Berlin Councils' committees and
convert forthcoming committee meetings to iCalendar data format and
write them to one iCalendar file per committee."""

import configparser
import http.client
import logging
import string
import textwrap
import time
import zlib

import lxml.html

logging.basicConfig(filename='.debug.log',
                    filemode='w',
                    format='%(filename)s:%(lineno)d:%(funcName)s - %(message)s',
                    level=logging.DEBUG)

HOST = 'www.berlin.de'
SESSION = http.client.HTTPSConnection(HOST)
REQUEST_DELAY = 3
REQUEST_HEADERS = {'Connection': 'keep-alive', 'Accept-Encoding': 'gzip'}

def read_configuration(filename):
    """Attempt to read and parse configuration data from *filename*.

    *filename* defaults to '.gremienkalender.conf'.
    When the file doesn't exist, return an empty dictionary.
    Otherwise, return a dictionary of name, value pairs."""
    try:
        config = configparser.ConfigParser()
        with open(filename, 'r') as conf:
            config.read_file(conf)
        return dict(config.items('DEFAULT'))
    except FileNotFoundError:
        return {}

def get_response_content(url):
    """Return the *url*s' response body as an lxml.html.HtmlElement."""
    logging.debug(url)
    time.sleep(REQUEST_DELAY)
    SESSION.request('GET', url, headers=REQUEST_HEADERS)
    response = SESSION.getresponse()

    if not response.status in range(200, 400):
        text = 'Request unsuccessful: %s %s'
        print(text % (response.status, url))
        return None

    content = response.read()

    if response.getheader('Set-Cookie'):
        cookies = response.getheader('Set-Cookie')
        cookies = cookies.split(',')
        cookies = [cookie.split(';')[0] for cookie in cookies]
        cookies = [cookie.strip() for cookie in cookies]
        cookies = '; '.join(cookies)
        REQUEST_HEADERS['Cookie'] = cookies

    try:
        content = zlib.decompress(content, 47)
    except zlib.error:
        pass
    try:
        content = content.decode('windows-1252', 'strict')
    except UnicodeDecodeError:
        content = content.decode('utf-8', 'replace')

    content = lxml.html.fromstring(content, base_url=url)
    content.make_links_absolute()

    return content

def extract_calendar_links(content):
    """Return a list of calendar links extracted from html content."""
    query_values = set()
    selector = '//select[@id="GRA"]/option'
    form_select = content.xpath(selector)
    for option in form_select:
        text_inactive = 'inaktiv' in option.text_content()
        class_inactive = option.get('class') == 'calWeek'
        if text_inactive or class_inactive:
            continue
        option_value = int(option.get('value'))
        query_values.add(option_value)

    if not query_values:
        return []

    base = content.base_url
    calendar_links = ['%s?GRA=%s' % (base, v) for v in query_values]
    return calendar_links

def date_range_query():
    """Return an URL query string."""
    today = time.localtime()
    year, month = today[0:2]
    query_template = '&YYV=%s&MMV=%s&YYB=%s&MMB=%s'
    if month < 11:
        return query_template % (year, month, year, month + 2)
    else:
        return query_template % (year, month, year + 1, month - 10)

def borough_slug_from_url(url):
    """Convert url into borough slug and return as string."""
    return url.split('/')[3][3:]

def borough_name_from_url(url):
    """Convert url into borough name and return as string."""
    borough = borough_slug_from_url(url)
    borough = borough.split('-')
    borough = [element.capitalize() for element in borough]
    borough = '-'.join(borough)
    borough = borough.replace('oe', 'ö')
    return borough

def extract_vevent_agenda(html):
    """Extract meeting agenda from html content and return it as string."""
    agenda = []
    for row in html.xpath('//tr[@class="zl11" or @class="zl12"]'):
        if not len(row) == 8:
            continue
        number = row[0][0].text_content()
        number = number.strip('Ö')
        number = number.strip()
        subject = row[3].text_content().strip()
        if not (subject and number):
            continue

        subject = subject.replace('\n', ' – ')

        document, link = '', ''
        if len(row[6]):
            document = row[6][0].text_content()
            link = row[6][0].get('href')

        if document:
            if link:
                agenda.append('%s: %s %s %s' % (number, document, subject, link))
            else:
                agenda.append('%s: %s %s' % (number, document, subject))
        else:
            agenda.append('%s: %s' % (number, subject))

    agenda_string = '\\n'.join(agenda)
    return agenda_string

def extract_vevent_details(html):
    """Extract meeting location, room & agenda and return a list of strings."""
    details = {}
    for key in ['Raum', 'Ort', 'Status', 'Anlass']:
        value = html.xpath('.//td[text()="%s:"]/following-sibling::td' % key)
        if not value:
            continue
        details[key] = value[0].text_content()
    details['Tagesordnung'] = extract_vevent_agenda(html)
    return details

def extract_vevent(row, vcalendar):
    """Extract event information from html table row and return vevent dict."""
    dtdate = row[0].text_content().strip()
    dttime = row[1].text_content().strip()
    if not (dtdate and dttime):
        return {}

    vevent = {}
    vevent['dtstart'] = '%s %s' % (dtdate[4:], dttime[:5])
    vevent['dtstart'] = time.strptime(vevent['dtstart'], '%d.%m.%Y %H:%M')
    vevent['dtstart'] = time.strftime('%Y%m%dT%H%M%S', vevent['dtstart'])

    vevent['uid'] = '%s@%s' % (vevent['dtstart'], vcalendar['uid'])

    vevent['dtstamp'] = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())

    vevent['summary'] = '%s: %s' % (vcalendar['bezirk'], vcalendar['gremium'])

    vevent['description'] = row[3].text_content().strip()

    vevent['url'] = ''
    vevent['location'] = ''

    containseventurl = (
        len(row[3]) and
        row[3][0].get('href') and
        row[3][0].get('href').startswith('https://www.berlin.de/ba-')
    )
    if containseventurl:
        vevent['url'] = row[3][0].get('href')
        vevent['description'] += '\\n' + vevent['url']

        html = get_response_content(vevent['url'])
        details = extract_vevent_details(html)

        if details.get('Ort'):
            if details.get('Raum'):
                vevent['location'] = '%s (%s)' % (details['Ort'], details['Raum'])
            else:
                vevent['location'] = details['Ort']

        if details.get('Anlass') or details.get('Status'):
            vevent['description'] += '\\n\\nArt der Sitzung: '
            if details.get('Anlass') or details.get('Status'):
                vevent['description'] += ', '.join((details['Anlass'], details['Status']))
            elif details.get('Status'):
                vevent['description'] += details['Status']
            elif details.get('Anlass'):
                vevent['description'] += details['Anlass']

        if details.get('Tagesordnung'):
            vevent['description'] += '\\n\\nTagesordnung:\\n'
            vevent['description'] += details['Tagesordnung']

    vevent['description'] += '\\n\\nStand: '
    vevent['description'] += time.strftime('%d.%m.%Y, %H:%M:%S', time.localtime())
    vevent['description'] += '\\nQuelle: '
    if vevent.get('url'):
        vevent['description'] += vevent['url']
    else:
        vevent['description'] += vcalendar['url']
    return vevent

def extract_vcalendar(html):
    """Return a list of committee meetings extracted from html content."""
    vcalendar = {}

    vcalendar['vevents'] = []

    vcalendar['url'] = html.base_url
    vcalendar['url'] = vcalendar['url'].split('&', 1)
    vcalendar['url'] = vcalendar['url'][0]

    vcalendar['bezirk'] = borough_name_from_url(vcalendar['url'])

    vcalendar['gremium'] = html.xpath('//table[@class="tl1"]/tr[1]/th[1]/text()')[0]
    vcalendar['gremium'] = vcalendar['gremium'].split('Sitzungen des Gremiums ')[1]
    vcalendar['gremium'] = vcalendar['gremium'].split(' im Zeitraum')[0]

    vcalendar['uid'] = '%03d.%s.berlin.de' % (
        int(vcalendar['url'].split('=', 1)[1]),
        borough_slug_from_url(vcalendar['url'])
    )

    vcalendar['calname'] = 'BVV %s: %s' % (vcalendar['bezirk'], vcalendar['gremium'])

    calendar_rows = html.xpath('//tr[@class="zl11" or @class="zl12"]')
    for row in calendar_rows:
        vevent = extract_vevent(row, vcalendar)
        vcalendar['vevents'].append(vevent)

    return vcalendar

def wrap_lines(text):
    """Wrap a lines of given text to a length of 70 characters."""
    width = 75
    wrapped_lines = []
    text_lines = text.split('\r\n')
    for line in text_lines:
        if len(line) <= width:
            wrapped_lines.append(line)
        else:
            first = True
            while line:
                nonascii = [c for c in line[:width] if c not in string.printable]
                nonasciiwidth = len(''.join(nonascii).encode('utf-8'))
                if first:
                    wrapped_lines.append(line[:width-nonasciiwidth])
                    line = line[width-nonasciiwidth:]
                    first = False
                    width -= 1
                else:
                    wrapped_lines.append(' '+line[:width-nonasciiwidth])
                    line = line[width-nonasciiwidth:]
    wrapped_text = '\r\n'.join(wrapped_lines)
    return wrapped_text

def write_vcalendar_file(vcalendar):
    """Create iCalendar data format strings and write them to files."""
    with open('vevent.template', 'r') as template_file:
        vevent_template = template_file.readlines()
        vevent_template = [line.strip() for line in vevent_template]
        vevent_template = '\r\n'.join(vevent_template)
        vevent_template += '\r\n'
    with open('vcalendar.template', 'r') as template_file:
        vcalendar_template = template_file.readlines()
        vcalendar_template = [line.strip() for line in vcalendar_template]
        vcalendar_template = '\r\n'.join(vcalendar_template)
        vcalendar_template += '\r\n'

    vevents = vcalendar['vevents']
    vcalendar['vevents'] = ''
    if not vevents:
        return False
    for vevent in vevents:
        vevent_string = string.Template(vevent_template)
        vevent_string = vevent_string.safe_substitute(vevent)
        vcalendar['vevents'] += vevent_string

    vcalendar_string = string.Template(vcalendar_template)
    vcalendar_string = vcalendar_string.safe_substitute(vcalendar)

    vcalendar_string = wrap_lines(vcalendar_string)

    vcalendar_file = '%s-%03d.ics' % (
        vcalendar['uid'].split('.')[1],
        int(vcalendar['uid'].split('.')[0])
    )
    with open(vcalendar_file, 'w') as icsfile:
        icsfile.write(vcalendar_string)

def main():
    """The main function."""
    config = read_configuration('.gremienkalender.conf')
    if config.get('request_user_agent'):
        REQUEST_HEADERS['User-Agent'] = config['request_user_agent']
    if config.get('request_from_email'):
        REQUEST_HEADERS['From'] = config['request_from_email']

    with open('input.txt', 'r') as textfile:
        input_urls = [line.strip() for line in textfile.readlines()]

    for borough_url in input_urls:
        html = get_response_content(borough_url)
        calendar_links = extract_calendar_links(html)
        for committee_url in calendar_links:
            link = committee_url+date_range_query()
            html = get_response_content(link)
            vcalendar = extract_vcalendar(html)
            if vcalendar:
                write_vcalendar_file(vcalendar)
    SESSION.close()

if __name__ == '__main__':
    main()
