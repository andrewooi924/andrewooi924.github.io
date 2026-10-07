"""Fixed-host, bounded HTTP client with robots checks and retry budgets."""
import ipaddress
import socket
import time
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import requests

HOSTS = {'www.onepiece-cardgame.com','yuyu-tei.jp','card.yuyu-tei.jp','www.cardrush-op.jp','dorasuta.jp'}
class Fetcher:
    def __init__(self, max_requests=200, delay=1.0):
        self.remaining=max_requests; self.delay=delay; self.robots={}; self.session=requests.Session()
        self.session.headers['User-Agent']='MostWantedPersonalCatalog/0.1'
    def _get(self,url,limit=8_000_000):
        for _ in range(4):
            u=urlparse(url)
            if u.scheme!='https' or u.hostname not in HOSTS or u.username or u.password or u.port not in (None,443):
                raise ValueError('Unapproved source URL')
            addresses=socket.getaddrinfo(u.hostname,443,type=socket.SOCK_STREAM)
            if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Non-public source address')
            if self.remaining<=0:raise RuntimeError('Request budget exhausted')
            self.remaining-=1; time.sleep(self.delay)
            with self.session.get(url,timeout=(10,30),allow_redirects=False,stream=True) as response:
                if response.status_code in (301,302,303,307,308):url=urljoin(url,response.headers['Location']);continue
                response.raise_for_status();parts=[];size=0
                for chunk in response.iter_content(65536):
                    size+=len(chunk)
                    if size>limit:raise ValueError('Response too large')
                    parts.append(chunk)
                return b''.join(parts)
        raise ValueError('Too many redirects')
    def get(self,url):
        u=urlparse(url)
        if u.hostname not in HOSTS:raise ValueError('Unapproved source host')
        origin='https://'+u.hostname
        if origin not in self.robots:
            parser=RobotFileParser();parser.set_url(origin+'/robots.txt')
            try:parser.parse(self._get(origin+'/robots.txt').decode('utf-8','replace').splitlines())
            except requests.HTTPError as e:
                if e.response.status_code!=404:raise
                parser.parse([])
            self.robots[origin]=parser
        if not self.robots[origin].can_fetch(self.session.headers['User-Agent'],url):raise ValueError('Disallowed by robots.txt')
        last=None
        for attempt in range(2):
            try:return self._get(url)
            except (requests.Timeout,requests.ConnectionError) as e:last=e
        raise last
