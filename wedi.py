from __future__ import unicode_literals
import regex as re
import requests
from bs4 import BeautifulSoup
import os, sys, shutil
import youtube_dl
import subprocess
import time
from selenium import webdriver

class MyLogger(object):
    def __init__(self):
        self.msgs = []
    def debug(self, msg):
        self.msgs.append(msg)
    def warning(self, msg):pass
    def error(self, msg):pass

class dummyGUI:
    def update_values(self, url='', dl='', perc='', size='', eta='', speed='', action=''):pass
    def set_stopevent(self, files=0, size=0, time=0):pass
    def add_to_list(self, name, replace=False):pass
    def add_to_urls(self, urls):pass
    def remove_from_urls(self, url):pass
    def update_action(self, text):pass
    def show_error(self, msg):pass

class services:
    def __init__(self, site, settings, GUI=None):
        os.environ['REQUESTS_CA_BUNDLE'] = os.path.join("certifi", "cacert.pem")
        self.extensive = settings['extensive']
        if site[-1:] != '/':
            site = site + '/'
        self.site = site
        self.domain = self.extract_domain(self.site)
        self.path = settings['path']
        if GUI:
            self.gui = GUI
        else:
            self.gui = dummyGUI()
        self.urls = []
        self.img_urls = []
        self.img_run = settings['images']['run']
        self.img_types = settings['images']['img_types']
        self.img_folder = ""
        self.doc_urls = []
        self.doc_run = settings['documents']['run']
        self.doc_types = settings['documents']['doc_types']
        self.doc_folder = ""
        self.vid_urls = []
        self.vid_run = settings['videos']['run']
        self.vid_types = settings['videos']['vid_types']
        self.vid_format = settings['videos']['format']
        self.vid_folder = ""
        self.aud_urls = []
        self.aud_run = settings['audios']['run']
        self.aud_types = settings['audios']['aud_types']
        self.aud_folder = ""
        self.dev_run = settings['dev']['run']
        self.dev_folder = ""

        self.video_streaming_services = ["vidstreaming", "rapidvideo", "streamango"]
        self.found_embedded_video_download_link = False

        self.force_stop = False

    def run(self):
        self.start_time = time.clock()
        self.connect()
        self.urls = self.extract_urls()
        if self.img_run:
            self.gui.add_to_urls(set(self.img_urls))
        if self.doc_run:
            self.gui.add_to_urls(set(self.doc_urls))
        if self.vid_run:
            self.gui.add_to_urls(set(self.vid_urls))
            self.gui.add_to_urls(set(self.ydl_urls.keys()))
        if self.aud_run:
            self.gui.add_to_urls(set(self.aud_urls))
        self.output_results()

    def stop(self):
        self.force_stop = True

    def my_hook(self, d):
        if self.force_stop:
            raise Exception("Stopping...")
        if d['status'] == 'finished':
            self.gui.update_values(url=d['filename'], dl=d['total_bytes'], perc='100.0%',
                size=d['total_bytes'], eta='0 Seconds', speed='0.0 KB/s',
                action='Done downloading, now converting...')
            self.gui.add_to_list(d['filename'])
            print('\nDone downloading, now converting...')
        else:
            self.gui.update_values(dl=d['downloaded_bytes'], perc=d['_percent_str'],
                 size=d['total_bytes'], eta=d['_eta_str'], speed=d['_speed_str'])
            print("Progress:" + d['_percent_str'], "of ~" + d['_total_bytes_str'],
                "at " + d['_speed_str'], "ETA " + d['_eta_str'], " "*5, end='\r')

    def extract_domain(self, site):
        domain = re.search('https?:\/\/[-_A-Za-z0-9\.]+\/', site)
        if not domain:
            return ""
        res = domain.group(0).split('://')
        protocol = res[0]
        domain = res[1]
        return (protocol, domain)

    def fix_url(self, url):
        if 'http' not in url and len(url) > 2:
            protocol = self.domain[0]
            domain_name = self.domain[1]
            if url[:2] == '//':
                return protocol + ':' + url
            if url[:1] == '/':
                url = url[1:]
            x = len(domain_name)
            if len(url) > x and url[:x] == domain_name:
                return protocol + '://' + url
            return protocol + '://' + domain_name + url
        if len(url) <= 2:
            return None
        return url

    def apply_special_rules(self, url):
        if "github" in self.domain[1]:
            url = url.replace('https://github.com/', 'https://raw.github.com/')
            url = url .replace('blob/', '')
            return url

        for service in self.video_streaming_services:
            if service in url and service not in self.domain[1]:
                self.ydl_urls[url] = None

        if "rapidvideo.com/e/" in url:
            url = url.replace("rapidvideo.com/e/", "rapidvideo.com/d/")
            response = requests.get(url, allow_redirects=True, stream=True)
            page_source = response.text
            soup = BeautifulSoup(page_source, 'html.parser')
            urls = re.findall('["\']((http|ftp)s?://.*?)["\']', page_source)
            for link in soup.find_all('a'):
                try:
                    urls.append((link['href'], ""))
                except:
                    pass
            urls = set(urls)
            res = []
            for url in urls:
                url = url[0]
                if self.is_vid_link(url):
                    res.append(url)
            if res:
                min_v = 2000
                max_v = -1
                best = worst = ""
                for link in res:
                    nbr = re.sub("[^0-9]", "", link.replace("mp4", ""))
                    nbr = nbr[len(nbr)-4:]
                    if nbr != "1080":
                        nbr = nbr[1:]
                    if int(nbr) > max_v:
                        max_v = int(nbr)
                        best = link
                    if int(nbr) < min_v:
                        min_v = int(nbr)
                        worst = link
                if "gogoanimes" in self.domain[1]:
                    filename = self.site.replace(self.domain[0] + "://" + self.domain[1], "")
                else:
                    filename = None
                if self.vid_format == "best":
                    self.ydl_urls[best] = filename
                else:
                    self.ydl_urls[worst] = filename
                #signal that a direct link to the video was found
                self.found_embedded_video_download_link = True
        return url

    '''
    removes all the urls in ydl_urls dict that has as a domain
    one of the predefined video streaming services
    '''
    def remove_other_video_streaming_services(self):
        keys_to_remove = []
        for url in self.ydl_urls:
            for service in self.video_streaming_services:
                if service in url:
                    keys_to_remove.append(url)
        for key in keys_to_remove:
            del self.ydl_urls[key]

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
        self.downloadpath = os.path.join(self.path, site_name)
        if len(self.downloadpath) > 200:
            self.downloadpath = self.downloadpath[:200] + '_'
        self.img_folder = os.path.join(self.downloadpath, "images")
        if not os.path.isdir(self.img_folder):
            os.makedirs(self.img_folder)
        self.doc_folder = os.path.join(self.downloadpath, "documents")
        if not os.path.isdir(self.doc_folder):
            os.makedirs(self.doc_folder)
        self.vid_folder = os.path.join(self.downloadpath, "videos")
        if not os.path.isdir(self.vid_folder):
            os.makedirs(self.vid_folder)
        self.aud_folder = os.path.join(self.downloadpath, "audios")
        if not os.path.isdir(self.aud_folder):
            os.makedirs(self.aud_folder)
        self.dev_folder = os.path.join(self.downloadpath, "dev")
        if not os.path.isdir(self.dev_folder):
            os.makedirs(self.dev_folder)

    def exit_with_error(self, error_message):
        print(error_message)
        self.gui.show_error(error_message)
        sys.exit(1)

    def get_executable_driver_path(self, browser):
        _platform = sys.platform
        if _platform == "linux" or _platform == "linux2":
            firefox_driver_path = os.path.join('drivers', 'geckodriver_linux')
            chrome_driver_path = os.path.join('drivers', 'chromedriver_linux')
        elif _platform == "darwin":
            firefox_driver_path = os.path.join('drivers', 'geckodriver_mac')
            chrome_driver_path = os.path.join('drivers', 'chromedriver_mac')
        elif _platform == "win32" or _platform == "win64":
            firefox_driver_path = os.path.join('drivers', 'geckodriver_win.exe')
            chrome_driver_path = os.path.join('drivers', 'chromedriver_win.exe')
        
        msg = "%s webdriver is missing! Try reinstalling the program."
        if browser == "firefox":
            if not os.path.isfile(firefox_driver_path):
                self.exit_with_error(msg %browser.capitalize())
            return firefox_driver_path
        elif browser == "chrome":
            if not os.path.isfile(chrome_driver_path):
                self.exit_with_error(msg %browser.capitalize())
            return chrome_driver_path
        else:
            self.exit_with_error("%s webdriver is not supported" %browser)

    def get_firefox_driver(self):
        executable_path = self.get_executable_driver_path("firefox")
        try:
            from selenium.webdriver.firefox.options import Options
            firefox_options = Options()
            firefox_options.add_argument("--headless")
            driver = webdriver.Firefox(executable_path=executable_path, firefox_options=firefox_options)
            return driver
        except:
            return None

    def get_chrome_driver(self):
        chrome_driver_path = self.get_executable_driver_path("chrome")
        try:
            from selenium.webdriver.chrome.options import Options
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            driver = webdriver.Chrome(executable_path=chrome_driver_path, chrome_options=chrome_options)
            return driver
        except:
            return None

    def connect_extensive(self):
        driver = self.get_firefox_driver()
        if not driver:
            driver = self.get_chrome_driver()
        if not driver:
            msg = "To use extensive run either Firefox or Chrome browser should be installed!"
            self.exit_with_error(msg)

        try:
            driver.get(self.site)
            self.page_source = driver.page_source
            driver.stop_client()
            driver.close()
            driver.quit()
            self.soup = BeautifulSoup(self.page_source, 'html.parser')
            self.response = requests.get(self.site, allow_redirects=True)
        except:
            msg = "Couldn't establish a connection to: " + self.site
            if len(msg) > 100:
                msg = msg[:97] + "..."
            self.exit_with_error(msg)

    def connect_normal(self):
        try:
            self.response = requests.get(self.site[:-1], allow_redirects=True, stream=True)
            content_type = self.response.headers.get('Content-Type').split(";")[0]
            if content_type != "text/html":
                self.page_source = ""
            else:
                self.page_source = self.response.text
            self.soup = BeautifulSoup(self.page_source, 'html.parser')
        except:
            msg = "Couldn't establish a connection to: " + self.site
            if len(msg) > 100:
                msg = msg[:97] + "..."
            self.exit_with_error(msg)

    def connect(self):
        msg = 'Establishing connection to ' + self.site
        if len(msg) > 100:
            msg = msg[:97] + "..."
        self.gui.update_action(msg)
        if self.extensive:
            self.connect_extensive()
        else:
            self.connect_normal()

    def extract_urls(self):
        self.gui.update_action("Extracting the urls from the website...")
        res = []
        urls = re.findall('["\']((http|ftp)s?://.*?)["\']', self.page_source)
        for link in self.soup.find_all('a'):
            try:
                urls.append((link['href'], ""))
            except:
                pass
        self.ydl_urls = {}
        self.ydl_urls[self.site[:-1]] = None
        urls.append((self.site[:-1], "")) #remove tailing /
        urls = set(urls)
        for url in urls:
            url = url[0]
            for link in url.split(" "):
                link = self.fix_url(link)
                if not link:
                    continue
                link = self.apply_special_rules(link)
                res.append(link)
                if (self.is_img_link(link)):
                    self.img_urls.append(link)
                elif (self.is_doc_link(link)):
                    self.doc_urls.append(link)
                #main url is handeled by youtube_dl for video and audio
                elif (link != self.site[:-1] and self.is_vid_link(link)):
                    self.vid_urls.append(link)
                elif (link != self.site[:-1] and self.is_aud_link(link)):
                    self.aud_urls.append(link)
        #To avoid downloading duplicates
        if self.found_embedded_video_download_link:
            self.remove_other_video_streaming_services()
        self.extract_images()
        return res

    def extract_images(self):
        res = re.findall(';pic=.*;', str(self.soup))
        for url in res:
            url = url[5:-1]
            url =  self.fix_url(url)
            if not url:
                continue
            url = self.apply_special_rules(url)
            self.img_urls.append(url)
            self.urls.append(url)

        img_tags = self.soup.find_all('img')
        for img in img_tags:
            url = ''
            if ' src=' in str(img):
                url = img['src']
            elif ' data-src=' in str(img):
                url = img['data-src']
            url =  self.fix_url(url)
            if not url:
                continue
            url = self.apply_special_rules(url)
            self.img_urls.append(url)
            self.urls.append(url)

    def is_img_link(self, url):
        for img_type in self.img_types:
            if ('.' + img_type) in url:
                return True
        return False

    def is_doc_link(self, url):
        for doc_type in self.doc_types:
            if ('.' + doc_type) in url[-len(doc_type) - 1:]:
                return True
        return False

    def is_vid_link(self, url):
        for vid_type in self.vid_types:
            if ('.' + vid_type) in url[-len(vid_type) - 1:]:
                return True
        return False

    def is_aud_link(self, url):
        for aud_type in self.aud_types:
            if ('.' + aud_type) in url[-len(aud_type) - 1:]:
                return True
        return False

    def create_filename(self, path, filename):
        tokens_to_be_replaced = ['*', '\\', '/', ':', '<', '>', '|', '?', '"', '\'']
        filename = self.multi_replace(tokens_to_be_replaced, '_', filename)
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

    def download_url(self, url, filename):
        self.gui.remove_from_urls(url)
        try:
            with open(filename, "wb") as f:
                print("\nDownloading %s" % url)
                response = requests.get(url, stream=True)
                total_length = response.headers.get('content-length')

                if total_length is None: # no content length header
                    self.gui.update_values(url=url)
                    f.write(response.content)
                else:
                    dl = 0
                    start = time.clock()
                    total_length = int(total_length)
                    for data in response.iter_content(chunk_size=4096):
                        if self.force_stop:
                            raise Exception("Stopping...")
                        dl += len(data)
                        f.write(data)
                        done = int(50 * dl / total_length)
                        sys.stdout.write("\r[%s%s]" % ('=' * done, ' ' * (50-done)) )
                        sys.stdout.flush()
                        if dl == total_length:
                            perc_str = '100.0%'
                            speed_str = '0.0 KB/s'
                            eta_str = '0 Seconds'
                        else:
                            perc_str = str(round(dl*100/total_length, 1)) + '%'
                            speed = dl/(time.clock() - start)
                            eta = int((total_length - dl) / speed)
                            if eta > 3600:
                                eta_str = str(round(eta / 3600, 2)) + ' Hours'
                            elif eta > 60:
                                eta_str = str(round(eta / 60, 2)) + ' Minutes'
                            else:
                                eta_str = str(eta) + ' Seconds'
                            if speed > 10**6:
                                speed_str = str(round(speed/10**6, 1)) + ' MB/s'
                            else:
                                speed_str = str(int(speed/1000)) + ' KB/s'
                        self.gui.update_values(url=url, dl=dl, perc=perc_str, size=total_length, eta=eta_str, speed=speed_str)
            self.gui.add_to_list(filename)
        except:
            msg = 'Failed to download ' + url
            if len(msg) > 100:
                msg = msg[:97] + "..."
            self.gui.update_action(msg)
            print("Falied to download!")

    def download_links(self, urls, types, output_dir):
        urls = set(urls)
        for url in urls:
            regex = r'/([^/]*[.]('
            for t in types:
                regex += t + '|'
            regex = regex[:-1] + '))'
            filename = re.findall(regex, url, re.IGNORECASE)
            if filename != None and len(filename) != 0:
                filename = filename[len(filename)-1][0]
                filename = self.create_filename(output_dir, filename)
                self.download_url(url, filename)
            else:
                filename = self.create_filename(output_dir, "noname." + types[0])
                self.download_url(url, filename)

    def ffmpeg_convert(self, in_file, out_file):
        #TODO support for linux and Mac
        _platform = sys.platform
        if _platform == "linux" or _platform == "linux2": # linux
            print("Converting in Linux is not supported yet!")
        elif _platform == "darwin": # MAC OS X
            print("Converting in MAC OS is not supported yet!")
        elif _platform == "win32" or _platform == "win64": # Windows
            ffmpeg_exe = "ffmpeg_win\\bin\\ffmpeg.exe"
            params = [ffmpeg_exe, '-i', in_file, out_file]
            subprocess.call(params, shell=False, close_fds=True)

    def ydl_audios(self):
        try:
            logger = MyLogger()
            filepath = os.path.join(self.aud_folder, '%(title)s.%(ext)s')
            ydl_opts = {
                'format': 'bestaudio/best',
                'noplaylist':True,
                'outtmpl': filepath,
                'logger': logger,
                'progress_hooks': [self.my_hook],
            }
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([self.site])
            msgs = logger.msgs
            for msg in msgs:
                if "[download] Destination: " in msg:
                    filename = msg[24:]
                    name = os.path.splitext(filename)[0]
                    extension = os.path.splitext(filename)[1]
                    if extension != ".mp3":
                        new_name = name + ".mp3"
                        self.ffmpeg_convert(filename, new_name)
                        self.gui.add_to_list(new_name, replace=True)
                        os.remove(filename)
                    break
        except Exception as e:
            self.gui.update_action(str(e))
            print(str(e))

    def ydl_video(self):
        filepath = os.path.join(self.vid_folder, '%(title)s.%(ext)s')
        ydl_opts = {
            'outtmpl': filepath,
            'format': self.vid_format,
            'logger': MyLogger(),
            'progress_hooks': [self.my_hook],
        }
        for url in self.ydl_urls:
            try:
                self.gui.remove_from_urls(url)
                self.gui.update_values(url=url)
                if self.ydl_urls[url]:
                    filepath = self.create_filename(self.vid_folder, self.ydl_urls[url])
                    temp_ydl_opts = ydl_opts.copy()
                    temp_ydl_opts['outtmpl'] = filepath + ".%(ext)s"
                    with youtube_dl.YoutubeDL(temp_ydl_opts) as ydl:
                        ydl.download([url])
                else:
                    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
            except Exception as e:
                self.gui.update_action(str(e))
                print(str(e))

    def output_dev(self):
        #General information about main url
        filename = os.path.join(self.dev_folder, 'mainURL.txt')
        with open(filename, 'wb') as f:
            line = self.site + "\n\n"
            f.write(line.encode('utf-8'))
            f.write("Headers:\n".encode('utf-8'))
            for head in self.response.headers:
                line = head + ": " + str(self.response.headers[head]) + "\n"
                f.write(line.encode('utf-8'))
            self.gui.add_to_list(filename)
        #Dump of the source code
        filename = os.path.join(self.dev_folder, 'source.html')
        with open(filename, 'wb') as f:
            f.write(self.soup.prettify().encode("utf-8"))
            self.gui.add_to_list(filename)
        #All the found urls
        filename = os.path.join(self.dev_folder, 'allURLs.txt')
        with open(filename, 'wb') as f:
            for url in set(self.urls):
                line = url + '\n'
                f.write(line.encode('utf-8'))
            self.gui.add_to_list(filename)
        if (len(self.img_urls) != 0):
            filename = os.path.join(self.dev_folder, 'imgURLs.txt')
            with open(filename, 'wb') as f:
                for url in set(self.img_urls):
                    line = url + '\n'
                    f.write(line.encode('utf-8'))
                self.gui.add_to_list(filename)
        if (len(self.doc_urls) != 0):
            filename = os.path.join(self.dev_folder, 'docURLs.txt')
            with open(filename, 'wb') as f:
                for url in set(self.doc_urls):
                    line = url + '\n'
                    f.write(line.encode('utf-8'))
                self.gui.add_to_list(filename)
        if (len(self.vid_urls) != 0):
            filename = os.path.join(self.dev_folder, 'vidURLs.txt')
            with open(filename, 'wb') as f:
                for url in self.ydl_urls:
                    line = url + '\n'
                    f.write(line.encode('utf-8'))
                self.gui.add_to_list(filename)
        if (len(self.aud_urls) != 0):
            filename = os.path.join(self.dev_folder, 'audURLs.txt')
            with open(filename, 'wb') as f:
                for url in set(self.aud_urls):
                    line = url + '\n'
                    f.write(line.encode('utf-8'))
                self.gui.add_to_list(filename)
        scripts = self.soup.find_all('script')
        if scripts:
            filename = os.path.join(self.dev_folder, 'scripts.html')
            with open(filename, 'wb') as f:
                for script in scripts:
                    line = "\n" + script.prettify() + "\n" + "*"*80
                    f.write(line.encode('utf-8'))
                self.gui.add_to_list(filename)

    def output_results(self):
        self.create_dest_folders()
        if self.dev_run:
            self.gui.update_action("Extracting the webpage information...")
            self.output_dev()
            print()
        if self.img_run:
            self.download_links(self.img_urls, self.img_types, self.img_folder)
            print()
        if self.doc_run:
            self.download_links(self.doc_urls, self.doc_types, self.doc_folder)
            print()
        if self.vid_run:
            #self.download_links(self.vid_urls, self.vid_types, self.vid_folder)
            for url in self.vid_urls:
                self.ydl_urls[url] = None
            print()
            print("Trying to extract video using youtube_dl...")
            self.gui.update_action("Trying to extract video using youtube_dl...")
            self.ydl_video()
            print()
        if self.aud_run:
            self.download_links(self.aud_urls, self.aud_types, self.aud_folder)
            print()
            print("Trying to extract audios using youtube_dl...")
            self.gui.update_action("Trying to extract audio using youtube_dl...")
            self.ydl_audios()
            print()
        self.rm_empty_dirs()
        print("Done.")
        self.gui.update_values(url=self.site, action="Done.")
        nbr_files, total_size = self.get_folder_info(self.downloadpath)
        runtime = time.clock() - self.start_time
        self.gui.set_stopevent(files=nbr_files, size=total_size, time=runtime)

    def open_path(self):
        _platform = sys.platform
        if _platform == "linux" or _platform == "linux2": # linux
            subprocess.Popen(["xdg-open", self.downloadpath])
        elif _platform == "darwin": # MAC OS X
            subprocess.Popen(["open", self.downloadpath])
        elif _platform == "win32" or _platform == "win64": # Windows
            os.startfile(self.downloadpath)

    def get_folder_info(self, path):
        total_size = 0
        nbr_files = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                nbr_files += 1
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        return nbr_files, total_size

    def rm_empty_dirs(self):
        if not os.listdir(self.vid_folder):
            os.rmdir(self.vid_folder)
        if not os.listdir(self.aud_folder):
            os.rmdir(self.aud_folder)
        if not os.listdir(self.doc_folder):
            os.rmdir(self.doc_folder)
        if not os.listdir(self.img_folder):
            os.rmdir(self.img_folder)
        if not os.listdir(self.dev_folder):
            os.rmdir(self.dev_folder)

if __name__ == "__main__":
    site = 'https://www.blocket.se/malmo/Mini_Cooper_Clubman_Pepper_120hk_6_vaxl_82169382.htm?ca=23_11&w=0'
    site = 'https://m2.ikea.com/se/sv/campaigns/nytt-laegre-pris-pub3c9e0c81' #js rendered page
    site = "https://www.youtube.com/watch?v=JR0BYMDWmVo"
    site = 'http://cs.lth.se/edan20/'
    site = 'https://www.bytbil.com/'
    site = "https://www3059.playercdn.net/1p-dl/0/-Yr5ejWImiGKNAQLwzX1Lw/1546394162/181101/498FWSRGZAZLCRFC4PCAP.mp4?name=anime_105980.mp4-720.mp4"
    site = "https://www.eit.lth.se/fileadmin/eit/courses/etsf10/ht18/Exercises/KRplusextraTut3solutions.pdf"
    site = 'https://www.dplay.se/videos/stories-from-norway/stories-from-norway-102'
    site = 'https://www.nordea.se/'
    site = "https://www.rapidvideo.com/e/FYOIHWGHES"
    site = "https://soundcloud.com/jahseh-onfroy/bad"
    site = "https://www.youtube.com/watch?v=VWIHxYvo6dk"
    site = "https://www09.gogoanimes.tv/tonari-seki-kun-episode-1"
    site = "https://www09.gogoanimes.tv/hetalia-axis-powers-episode-1"
    site = "https://github.com/harvitronix/neural-network-genetic-algorithm" #debugg docs
    site = "https://vidstream.co/download?id=MTE0MTM0&typesub=Gogoanime-SUB&title=Tate+no+Yuusha+no+Nariagari+Episode+8"
    site = "https://www.rapidvideo.com/d/G0MW1FLIA5"
    site = 'https://www.youtube.com/watch?v=zmr2I8caF0c' #small

    path = "wedi_downloads"
    extensive = False
    img_types = ['jpg', 'jpeg', 'png', 'gif', 'svg']
    doc_types = ['txt', 'py', 'java', 'php', 'pdf', 'md', 'gitignore', 'c']
    vid_types = ['mp4', 'avi', 'mpeg', 'mpg', 'wmv', 'mov', 'flv', 'swf', 'mkv', '3gp', 'webm', 'ogg']
    aud_types = ['mp3', 'aac', 'wma', 'wav', 'm4a']
    img_settings = {'run':False, 'img_types':img_types}
    doc_settings = {'run':False, 'doc_types':doc_types}
    vid_settings = {'run':True, 'vid_types':vid_types, 'format':'best'}
    aud_settings = {'run':False, 'aud_types':aud_types}
    dev_settings = {'run':True}
    settings = {'path':path, 'extensive':extensive, 'images':img_settings, 'documents':doc_settings, 'videos':vid_settings, 'audios':aud_settings, 'dev':dev_settings}
    services = services(site, settings)
    services.run()

