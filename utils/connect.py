import pickle
import datetime
import os
import tempfile
from urllib.parse import urlparse
import requests
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

#To debug requests/retry tentatives
#import logging
#logging.basicConfig(level=logging.DEBUG)

DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36"
DEFAULT_SESSION_APPENDIX = "_session.dat"
DEFAULT_MAX_SESSION_TIME = 30 * 60  # 30 minutes
RETRY_STATUS_CODES = [408, 429, 444, 498, 499, 500, 502, 503, 504]
RETRIES = Retry(total=5, backoff_factor=0.5, respect_retry_after_header=False, status_forcelist=RETRY_STATUS_CODES)

class SRRDB_LOGIN:
    """
	https://stackoverflow.com/questions/12737740/python-requests-and-persistent-sessions
    a class which handles and saves login sessions. It also keeps track of proxy settings.
    It does also maintine a cache-file for restoring session data from earlier
    script executions.
    """
    def __init__(self,
                 loginUrl,
                 loginData,
                 loginTestUrl,
                 loginTestString,
                 sessionFileAppendix = DEFAULT_SESSION_APPENDIX,
                 maxSessionTimeSeconds = DEFAULT_MAX_SESSION_TIME,
                 proxies = None,
                 userAgent = DEFAULT_USER_AGENT,
                 debug = False,
                 forceLogin = False):
        """
        save some information needed to login the session
        you'll have to provide 'loginTestString' which will be looked for in the
        responses html to make sure, you've properly been logged in
        'proxies' is of format { 'https' : 'https://user:pass@server:port', 'http' : ...
        'loginData' will be sent as post data (dictionary of id : value).
        'maxSessionTimeSeconds' will be used to determine when to re-login.
        """
        urlData = urlparse(loginUrl)

        self.loginUrl = loginUrl
        self.loginData = loginData
        self.loginTestUrl = loginTestUrl
        self.loginTestString = loginTestString
        self.sessionFile = os.path.join(tempfile.gettempdir(), urlparse(loginUrl).netloc + sessionFileAppendix)
        self.maxSessionTime = maxSessionTimeSeconds
        self.proxies = proxies
        self.userAgent = userAgent
        self.debug = debug

        self.logged_in = self.initialize_session(forceLogin)

    def modification_date(self, filename):
        t = os.path.getmtime(filename)
        return datetime.datetime.fromtimestamp(t)

    def initialize_session(self, forceLogin):
        if not forceLogin and self.load_session_from_cache():
            return True
        return self.create_new_session()

    def load_session_from_cache(self):
        if os.path.exists(self.sessionFile):
            last_modification = (datetime.datetime.now() - self.modification_date(self.sessionFile)).seconds
            if last_modification < self.maxSessionTime:
                with open(self.sessionFile, 'rb') as f:
                    self.session = pickle.load(f)
                    if self.debug:
                        print(f"\t - Loaded session from cache (last access {last_modification}s ago)")
                    return True
        return False

    def create_new_session(self):
        self.session = requests.Session()
        self.session.headers.update({"user-agent": self.userAgent})
        self.session.mount('https://', HTTPAdapter(max_retries=RETRIES))

        if self.loginData:
            res = self.session.post(self.loginUrl, data=self.loginData, proxies=self.proxies)
            if self.debug:
                print("\t - Created new session with login")
            if self.loginTestUrl and self.loginTestString:
                return self.verify_login()

        self.save_session_to_cache()
        return False

    def verify_login(self):
        res = self.session.get(self.loginTestUrl)
        if self.loginTestString.lower() not in res.text.lower():
            #raise ValueError(f"Could not log into provided site '{self.loginUrl}' (did not find successful login string)")
            if self.debug:
                print(f"Login failed: could not find '{self.loginTestString}' in the response from {self.loginTestUrl}")
            return False

        if self.debug:
            print("Login successful")
        return True

    def save_session_to_cache(self):
        # always save (to update timeout)
        with open(self.sessionFile, "wb") as f:
            pickle.dump(self.session, f)
            if self.debug:
                print(f"\n\t - Updated session cache-file {self.sessionFile}")

    def retrieve_content(self, url, method="get", postData=None, **kwargs):
        if method.lower() == 'get':
            res = self.session.get(url, proxies=self.proxies, **kwargs)
        else:
            res = self.session.post(url, data=postData, proxies=self.proxies, **kwargs)

        # the session has been updated on the server, so also update in cache
        self.save_session_to_cache()
        return res
        