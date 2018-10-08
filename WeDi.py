import regex as re
import requests
from bs4 import BeautifulSoup
import os

class services:
    def __init__(self, site, path):
        self.site = site
        self.domain = self.extract_domain(site)
        self.path = path
        self.img_urls = []
        self.doc_urls = []
        self.img_types = ['jpg', 'jpeg', 'png', 'gif']
        self.doc_types = ['py']
        self.connect()
        self.extract_urls()

    def extract_domain(self, site):
        domain = re.search('(http|ftp)s?[:\/\/]+[A-Za-z0-9\.]+\/', site)
        if not domain:
            return ""
        res = domain.group(0).split('://')
        protocol = res[0]
        domain = res[1]
        return (protocol, domain)

    def fix_url(self, url):
        if 'http' not in url:
            if url[:1] == '/':
                url = url[1:]
            protocol = self.domain[0]
            domain_name = self.domain[1]
            x = len(domain_name)
            if len(url) > x and url[:x] == domain_name:
                return protocol + '://' + url
            return protocol + '://' + domain_name + url
        return url

    def apply_special_rules(self, url):
        if ("github" in self.domain[1]):
            url = url.replace('https://github.com/', 'https://raw.github.com/')
            url = url .replace('blob/', '')
            return url

    def multi_replace(self, tokens_to_be_replaced, replace_with, text):
        for token in tokens_to_be_replaced:
            text = text.replace(token, replace_with)
        while(text[:1] == replace_with):
            text = text[1:]
        while(text[-1:] == replace_with):
            text = text[:-1]
        return text

    def create_dest_folders(self):
        tokens_to_be_replaced = ['https://', 'http://', 'www.', '*', '\\', '/', ':', '<', '>', '|', '?', '"', '\'']
        site_name = self.multi_replace(tokens_to_be_replaced, '_', self.site)
        path = os.path.join(site_name, self.path)
        if (len(self.img_urls) != 0) :
            self.img_folder = os.path.join(path, "images")
            if not os.path.isdir(self.img_folder):
                os.makedirs(self.img_folder)
        if (len(self.doc_urls) != 0) :
            self.doc_folder = os.path.join(path, "documents")
            if not os.path.isdir(self.doc_folder):
                os.makedirs(self.doc_folder)

    def connect(self):
        self.response = requests.get(self.site, allow_redirects=True)
        # print(self.response.text)
        #print(self.response.headers)
        self.soup = BeautifulSoup(self.response.text, 'html.parser')

    def extract_urls(self):
        self.urls = re.findall('["\']((http|ftp)s?://.*?)["\']', self.response.text)
        self.urls += [(a['href'], "") for a in self.soup.find_all('a')]
        self.urls = set(self.urls)
        for url in self.urls:
            url = url[0]
            #print(url)
            for link in url.split(" "):
                link = self.fix_url(link)
                link = self.apply_special_rules(link)
                if (self.is_img_link(link)):
                    self.img_urls.append(link)
                if (self.is_doc_link(link)):
                    self.doc_urls.append(link)

    def extract_images(self):
        img_tags = self.soup.find_all('img')

        for img in img_tags:
            url = ''
            if ' src=' in str(img):
                url = img['src']
            elif ' data-src=' in str(img):
                url = img['data-src']
            if (self.is_img_link(url)):
                self.img_urls.append(url)

    def is_img_link(self, url):
        for img_type in self.img_types:
            if ('.' + img_type) in url:
                return True
        return False

    def is_doc_link(self, url):
        for doc_type in self.doc_types:
            if ('.' + doc_type) in url:
                return True
        return False

    def create_filename(self, path, filename):
        filename = os.path.join(path, filename)
        while os.path.exists(filename):
            temp = os.path.basename(filename).split('.')
            ftype = temp[len(temp)-1]
            name = '.'.join(temp[:-1])
            match = re.findall('[(][0-9]+[)].' + ftype, filename)
            if match:
                nbr = int(re.sub('[^0-9]','', match[0])) + 1
                filename = filename.replace(match[0], '')
                filename = filename + '(' + str(nbr) +').' + ftype
            else:
                filename = name + '(1).' + ftype
                filename = os.path.join(path, filename)
        return filename

    def output_results(self):
        self.create_dest_folders()
        #output for images
        # self.img_urls = set(self.img_urls)
        counter = 0
        for url in self.img_urls:
            print(url)
            # regex = r'/([\w_-]+[.]('
            # for img_type in self.img_types:
            #     regex += img_type + '|'
            # regex = regex[:-1] + r')'
            # filename = re.search(regex, url, re.IGNORECASE)
            filename = re.search(r'/([\w_-]+[.](jpg|gif|png|jpeg))', url, re.IGNORECASE) #TODO makes it dynamic
            if filename == None:
                filename = re.sub('[^0-9a-zA-Z]+', '', url) + ".jpg"
            else:
                filename = filename.group(1)
            filename = self.create_filename(self.img_folder, filename)
            print(filename)
            with open(filename, 'wb') as f:
                response = requests.get(url)
                f.write(response.content)
            # counter +=1
            # if counter == 3:
            #     break

        #output for documents
        self.doc_urls = set(self.doc_urls)
        for url in self.doc_urls:
            print(url)
            filename = re.search(r'/([\w_-]+[.](py))', url, re.IGNORECASE) #TODO makes it dynamic
            if filename == None:
                filename = re.sub('[^0-9a-zA-Z]+', '', url) + ".txt"
            else:
                filename = filename.group(1)
            filename = self.create_filename(self.doc_folder, filename)
            with open(filename, 'wb') as f:
                response = requests.get(url)
                f.write(response.content)

if __name__ == "__main__":
    site = 'https://github.com/pnugues/ilppp/tree/master/programs/labs/chunking/chunker_python/'
    services = services(site, "")
    services.extract_images()
    services.output_results()

