import json
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from yyt_scrapper import parse_listing_html

CODE=re.compile(r'(?:OP|ST|EB|PRB)\d{2}-\d{3}|P-\d{3}')

def official(html, url):
    soup=BeautifulSoup(html,'html.parser');rows=[]
    for node in soup.select('.modalCol'):
        info=node.select('.infoCol span');img=node.select_one('.frontCol img');name=node.select_one('.cardName')
        if not info or img is None:continue
        src=img.get('data-src') or img.get('src')
        if not src:continue
        fields={k:(node.select_one(sel).get_text(' ',strip=True) if node.select_one(sel) else '') for k,sel in
                {'effect':'.text','power':'.power','color':'.color','release':'.getInfo','cost':'.cost','counter':'.counter','feature':'.feature'}.items()}
        rows.append({'source':'bandai','source_id':node.get('id') or urlparse(src).path.rsplit('/',1)[-1],
            'code':info[0].get_text(strip=True),'rarity':info[1].get_text(strip=True) if len(info)>1 else '',
            'category':info[2].get_text(strip=True) if len(info)>2 else '',
            'name':name.get_text(strip=True) if name else '', 'image':urljoin(url,src),'url':url,**fields})
    return rows

def discover_official(html):
    soup=BeautifulSoup(html,'html.parser')
    return sorted({'https://www.onepiece-cardgame.com/cardlist/?series='+o['value']
                   for o in soup.select('option[value]') if re.fullmatch(r'\d{6}',o['value'])})

def discover_yuyutei(html):
    soup=BeautifulSoup(html,'html.parser');urls=set()
    for a in soup.select('a[href]'):
        url=urljoin('https://yuyu-tei.jp/',a['href'])
        if re.fullmatch(r'https://yuyu-tei\.jp/sell/opc/s/(?:op\d+|st\d+|eb\d+|prb\d+|don|promo-[a-z0-9-]+)',url):urls.add(url)
    return sorted(urls)

def yuyutei(html,url):
    rows=parse_listing_html(html,url.rstrip('/').split('/')[-1])
    return [{'source':'yuyutei','source_id':f"{r['set_code']}_{r['yuyutei_cid']}",'code':r['card_code'],
             'title':r['name'],'price':r['price'],'currency':'JPY','in_stock':not r['sold_out'],
             'condition':'standard','image':r['image'],'url':r['product_url'],'tags':r['variant']} for r in rows]

def cardrush(html,url):
    """Extract product cards, not unrelated prices or condition assumptions."""
    soup=BeautifulSoup(html,'html.parser');rows={}
    for a in soup.select('a[href]'):
        product=urljoin(url,a['href']);m=re.fullmatch(r'https://www\.cardrush-op\.jp/product/(\+?\d+)',product)
        if not m:continue
        title=a.get_text(' ',strip=True)
        if not CODE.search(title):continue
        node=a
        for _ in range(5):
            if not node.parent:break
            text=node.get_text(' ',strip=True)
            # Only a container with a single product identity may supply its price.
            ids={re.search(r'/product/(\d+)',x['href']).group(1) for x in node.select('a[href]') if re.search(r'/product/(\d+)',x['href'])}
            price=re.search(r'([\d,]+)\s*円',text)
            if price and len(ids)==1:
                image=node.select_one('img');rows[m[1]]={'source':'cardrush','source_id':m[1],'code':CODE.search(title).group(),
                  'title':title,'price':int(price.group(1).replace(',','')),'currency':'JPY',
                  'in_stock':False if '在庫なし' in text or 'SOLD OUT' in text.upper() else (True if re.search(r'在庫数\s*[1-9]',text) else None),
                  'condition':'unknown','url':product,'image':urljoin(url,image.get('src','')) if image else None}
                break
            node=node.parent
    return list(rows.values())

def dorasuta(html,url):
    """Conservative structured-data adapter. Unsupported pages fail validation."""
    soup=BeautifulSoup(html,'html.parser');rows=[]
    def walk(x):
        if isinstance(x,list):
            for i in x:yield from walk(i)
        elif isinstance(x,dict):
            yield x
            for v in x.values():
                if isinstance(v,(dict,list)):yield from walk(v)
    for tag in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(tag.string or tag.get_text())
        except (ValueError,TypeError):continue
        for x in walk(data):
            if x.get('@type')!='Product':continue
            title=x.get('name','');code=CODE.search(title);offer=x.get('offers',{})
            if not code or not isinstance(offer,dict) or offer.get('priceCurrency')!='JPY':continue
            try:price=int(offer['price'])
            except (KeyError,TypeError,ValueError):continue
            key=x.get('sku') or x.get('productID')
            if not key:continue
            rows.append({'source':'dorasuta','source_id':str(key),'code':code.group(),'title':title,'price':price,
              'currency':'JPY','in_stock':str(offer.get('availability','')).endswith('/InStock'),
              'condition':'unknown','image':None,'url':url})
    return rows
