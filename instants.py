import re

import requests
from loguru import logger
from bs4 import BeautifulSoup

class InstantsCrawler:
    BASE_URL = 'https://www.myinstants.com'

    def get_search_results(self, search):
        html = requests.get(f'{self.BASE_URL}/search?name={search}')
        soup = BeautifulSoup(html.content, 'html.parser')
        instants = soup.select('.instant')
        return instants[:25]

    def get_single_search_result(self, search):
        results = self.get_search_results(search)
        return results[0] if results else None

    def get_instant_name(self, instant):
        instant_link = instant.select_one('.instant-link')
        return instant_link.text

    def get_instant_mp3_link(self, instant):
        mp3_div = instant.select_one('.small-button')
        mouse_event = mp3_div.attrs.get('onmousedown')
        mp3_link = re.search('/media.+.mp3', mouse_event).group(0)
        return f'{self.BASE_URL}{mp3_link}'

    def get_instant_link(self, instant):
        link_attrs = instant.select_one('.instant-link').attrs
        instant_link = link_attrs['href']
        return f'{self.BASE_URL}{instant_link}'

    def get_instant_details(self, instant):
        instant_link = self.get_instant_link(instant)
        html = requests.get(instant_link)
        soup = BeautifulSoup(html.content, 'html.parser')
        title = self.get_instant_title(soup)
        description = self.get_instant_description(soup)
        likes = self.get_instant_likes(soup)
        uploader_name = self.get_instant_uploader_name(soup)
        uploader_url = self.get_instant_uploader_url(soup)
        views = self.get_instant_views(soup)
        instant_details = {
            'title': title,
            'description': description,
            'likes': likes,
            'uploader_name': uploader_name,
            'uploader_url': uploader_url,
            'views': views,
        }
        return instant_details

    def get_instant_title(self, soup):
        try:
            return soup.select_one('#instant-page-title').text
        except AttributeError:
            return None

    def get_instant_description(self, soup):
        try:
            return soup.select_one('#instant-page-description').p.text
        except AttributeError:
            return None

    def get_instant_likes(self, soup):
        try:
            return soup.select_one('#instant-page-likes').b.text
        except AttributeError:
            return None

    def get_instant_uploader_name(self, soup):
        try:
            views_div = soup.select_one('#instant-page-likes').nextSibling.nextSibling
            return views_div.a.text
        except AttributeError:
            return 'Anonymous'

    def get_instant_uploader_url(self, soup):
        try:
            views_div = soup.select_one('#instant-page-likes').nextSibling.nextSibling
            href_attr = views_div.a.attrs.get('href')
            return f'{self.BASE_URL}{href_attr}'
        except AttributeError:
            return None

    def get_instant_views(self, soup):
        try:
            views_div = soup.select_one('#instant-page-likes').nextSibling.nextSibling
            return re.search('[\d,]+ *views', views_div.text).group(0)
        except AttributeError:
            return None
