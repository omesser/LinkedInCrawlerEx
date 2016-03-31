#!/usr/local/bin/python
"""

WEB API:

<address>/scrape?url=https://www.linkedin.com/in/studentsample
<address>/search?first=student&last=sample
<address>/skillcount?first=student&last=sample

"""
from lxml import html
import requests
import json
import traceback
from flask import Flask, request

# --------------  Scraper logic ------------------


class LinkedInScraper(object):
    def __init__(self):
        # urls:
        self.pubsearch_url = "https://www.linkedin.com/pub/dir/?first={first}&last={last}" \
        # define some xpaths:
            # for public profile:
        self.xpath_fullname = "//h1[@id='name']/text()"
        self.xpath_title = "//p[@class='headline title']/text()"
        self.xpath_summary = "//section[@id='summary']/div[@class='description']/p/text()"
        self.xpath_positions_list = "//ul[@class='positions']/li[@class='position']"
            # relative, inside a position element:
        self.xpath_position_title = "./header/h4[@class='item-title']/a/text()"
        self.xpath_position_time = "./div[@class='meta']/span[@class='date-range']/text()"
        self.xpath_top_skill_list = "//li[@class='skill']/a/span[@class='wrap']/text()"
        self.xpath_extra_skill_list = "//li[@class='skill extra']/a/span[@class='wrap']/text()"
            # in public search page:
        self.xpath_candidates_fullname_list = "//div[@class='profile-card']/div[@class='content']/h3/a/text()"
        self.xpath_candidates_puburls_list = "//a[@class='hide-desktop public-profile-link']"
        self.headers1 = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}

    #   self.headers2 = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    #           'Accept-Encoding': 'gzip, deflate',
    #           'Accept-Language': 'ru,en-US;q=0.8,en;q=0.6,he;q=0.4',
    #           'Content-Type': 'application/x-www-form-urlencoded',
    #           'Connection': 'keep-alive',
    #           'Content-Length': '104',
    #           'Host': 'www.histdata.com',
    #           'Origin': 'http://www.histdata.com',
    #           'Upgrade-Insecure-Requests': '1',
    #           'Referer': TEST_URL,
    #           'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/'
    #                         '537.36 (           KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36',
    #           }

    def scrape_profile(self, profileurl=None, only_top_skills=False):
        """
        Public profile scraping logic, class entry point
        """
        # For consistency
        fullname = None
        title = None
        current_position = None
        summary = None
        skills = []
        error = "None"

        try:
            if not profileurl:
                raise IOError("No url given to scrape_profile")

            response = requests.get(profileurl, headers=self.headers1)
            # Get them
            tree = html.fromstring(response.content)
            fullname = tree.xpath(self.xpath_fullname)
            if isinstance(fullname, list):
                fullname = fullname[0]
            title = tree.xpath(self.xpath_title)
            if isinstance(title, list):
                title = title[0]
            summary = tree.xpath(self.xpath_summary)
            if isinstance(summary, list):
                summary = self._norm_str_("\n".join(summary))
            positions_list = tree.xpath(self.xpath_positions_list)
            current_position = None
            for pos in positions_list:
                pos_title = pos.xpath(self.xpath_position_title)
                if isinstance(pos_title, list):
                    pos_title = pos_title[0]
                time = pos.xpath(self.xpath_position_time)
                if isinstance(time, list):
                    time = time[0]
                if "present" in time.lower():
                    current_position = pos_title
                    break

            skills_top = tree.xpath(self.xpath_top_skill_list)
            skills_extra = []
            if not only_top_skills:
                skills_extra = tree.xpath(self.xpath_extra_skill_list)
            skills = skills_top + skills_extra
            skills = [self._norm_str_(s) for s in skills]
        except Exception as e:
            # traceback.format_exc()
            error = e.message

        crawl_output = {"name": fullname,
                        "title": title,
                        "current position": current_position,
                        "summary": summary,
                        "skills": skills,
                        "error": error,
                        }

        return json.dumps(crawl_output)

    def search_people(self, firstname=None, lastname=None):
        """
        Profile search capability logic, class entry point
        """
        # For consistency
        proffessionals = []
        profileurls = []
        error = "None"
        try:
            if not firstname or not lastname:
                raise IOError("Bad parameters to search_poeple() Please provide firstname, lastname")
            pubsearch_url = self.pubsearch_url.format(first=firstname, last=lastname)
            response = requests.get(pubsearch_url, headers=self.headers1)
            proffessionals, profileurls = self._scrape_search_poeple_in_tree(response)
        except Exception as e:
            # traceback.format_exc()
            error = e.message

        search_res = []
        # Do at least one for the error:
        if not proffessionals:
            search_res.append({"name": None,
                               "profileurl": None,
                               "error": error
                               })
        else:
            for i in xrange(0, len(proffessionals), 1):
                search_res.append({"name": proffessionals[i],
                                   "profileurl": profileurls[i],
                                   "error": error
                                   })

        return json.dumps(search_res)

    def search_for_top_skills(self, firstname=None, lastname=None):
        """
        Uses search_people() and scrape_profile() to search and fetch "top" (none-folded)
        skill count, class entry point
        """
        res = []

        public_profiles = json.loads(self.search_people(firstname=firstname, lastname=lastname))
        for profile in public_profiles:
            profiledata = json.loads(self.scrape_profile(profile["profileurl"], only_top_skills=True))
            res.append({"name": profiledata["name"],
                        "profileurl": profile["profileurl"],
                        "skillcount": len(profiledata["skills"]),
                        "error": profiledata["error"],
                        })

        return json.dumps(res)

    def _scrape_search_poeple_in_tree(self, response):
        """
        Given public profile search response, provides names and and profile urls data.
        Handles auto-rerouting, which happens if 1 exact match found.
        """
        tree = html.fromstring(response.content)
        # If there's only 1 response
        fullname = tree.xpath(self.xpath_fullname)
        # redirect - exact single hit
        if response.history and response.history[0].is_redirect:  # == status code 307
            profileurl = response.url
            return [fullname[0]], [self._norm_str_(profileurl)]
        # Get all candidates:
        fullnames = tree.xpath(self.xpath_candidates_fullname_list)
        prof_url_els = tree.xpath(self.xpath_candidates_puburls_list)
        profileurls = [url.attrib['href'] for url in prof_url_els]
        return fullnames, profileurls

    @staticmethod
    def _norm_str_(stri):
        """ Get rid of unicode none-standard chars """
        # print stri
        return stri.encode('ascii', 'ignore')

scraper_ins = LinkedInScraper()

# --------------  flask WSGI bindings ------------------

app = Flask(__name__)


@app.route("/")
def test():
    """ up test """
    print "testing, alive"


@app.route("/scrape", methods=["GET"])
def scrapeprofile():
    """ Given a public profile url, returns some scraped profile data"""
    puburl = request.args.get("url")
    # print puburl
    return scraper_ins.scrape_profile(puburl)


@app.route("/search")
def profilesearch():
    """ Given a first and last names, does the linkedin profile search and returns basic data about results """
    first = request.args.get("first")
    last = request.args.get("last")
    # print first
    # print last
    return scraper_ins.search_people(firstname=first, lastname=last)


@app.route("/skillcount")
def skillCountsearch():
    """
    Given a first and last names, does the linkedin profile search, and returns data about results + counts of
    top skills per profile fetched
    """
    first = request.args.get("first")
    last = request.args.get("last")
    # print first
    # print last
    return scraper_ins.search_for_top_skills(firstname=first, lastname=last)


if __name__ == "__main__":
    app.run(port="80")

    ### Testing the scraper methods directly ###
    # TEST_URLS = [
    #     'http://www.linkedin.com/in/odedmesser',
    #     'http://www.linkedin.com/in/studentsample',
    # ]

    # scraper = LinkedInScraper()
    # for profile_url in TEST_URLS:
    #     json_data = scraper.scrape_profile(profile_url)
    #     json_parsed = json.loads(json_data)
    #     print json.dumps(json_parsed, indent=4, sort_keys=True)
    # for fname, lname in [("sample", "student"), ("oded", "messer")]:
    #     json_res = scraper.search_people(firstname=fname, lastname=lname)
    #     json_parsed = json.loads(json_res)
    #     print json.dumps(json_parsed, indent=4, sort_keys=True)
    #     json_res = scraper.search_for_top_skills(firstname=fname, lastname=lname)
    #     json_parsed = json.loads(json_res)
    #     print json.dumps(json_parsed, indent=4, sort_keys=True)

