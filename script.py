from pathlib import Path
from os import system
from os.path import exists
import json
import re
import random
import requests
from bs4 import BeautifulSoup

BIRD_URLS = "birdurls.txt"
ANKI_MEDIA = ".local/share/Anki2/User 1/collection.media/"
MAX_IMAGES = 5
CSV_PATH = "birds.csv"


class Bird:
    def __init__(self, *args):
        args = args[0]
        for arg in args:
            if isinstance(arg, str):
                # There is sometimes spurious whitespace
                arg = arg.strip()

        self.name = args[0]
        self.binomial = args[1].capitalize()
        self.group = args[2].capitalize()
        self.status = args[3]
        self.identify = args[4]
        self.key_facts = args[5]
        self.url = args[6]
        self.image_urls = args[7]
        self.call_url = args[8]
        self.distribution_url = args[9]

    def __str__(self):
        if self.call_url is None:
            sound_str = ""
        else:
            sound_str = f'[sound:{self.media_filename("call", "", "mp3")}]'

        image_fields = []
        for i in range(MAX_IMAGES):
            if i < len(self.image_urls):
                image_fields.append(normalize_csv(self.image_urls[i]))
                image_fields.append(
                    normalize_csv(
                        f'<img src="{self.media_filename("image", i + 1, "jpg")}">'
                    )
                )
            else:
                image_fields.append('""')
                image_fields.append('""')

        joined = ",".join(
            [
                normalize_csv(self.name),
                normalize_csv(self.binomial),
                normalize_csv(self.identify),
                normalize_csv(self.cloze()),
                normalize_csv(self.url),
            ]
            + image_fields
            + [
                normalize_csv(self.call_url),
                normalize_csv(sound_str),
                normalize_csv(normalize_tag(self.group)),
            ]
        )

        return joined

    def numbers(self):
        """Return an estimate of the number of `bird` in the UK, based on the
        'UK breeding birds' section of `bird`'s 'Key facts'."""
        reg = re.compile(r"[\d,\.]*")
        breeding_birds = self.key_facts.get("ukBreedingBirds", "0").strip()
        number_string = reg.search(breeding_birds).group().replace(",", "")
        if number_string == "":
            return 0
        number = float(number_string)
        multipliers = [["million", 1000000], ["pair", 2]]
        for mult in multipliers:
            reg = re.compile(mult[0], re.IGNORECASE)
            if reg.search(breeding_birds) is not None:
                number *= mult[1]
        return round(number)

    def media_filename(self, media_type, qualifier, ext):
        if media_type == "call" and self.call_url is None:
            return ""
        reg = re.compile("/([^/]*)$")
        name = reg.search(self.url).group(1)
        return f"bird_{media_type}_{name}{qualifier}.{ext}"

    def download_media(self):
        anki_path = Path.home() / Path(ANKI_MEDIA)

        for i in range(MAX_IMAGES):
            if i < len(self.image_urls):
                image_path = anki_path / self.media_filename("image", i + 1, "jpg")
                if exists(image_path):
                    print(f"Found file {image_path}")
                else:
                    compression = 20
                    command = f'ffmpeg -i "{self.image_urls[i]}" -q:v {compression} "{image_path}"'
                    system(command)

        call_path = anki_path / self.media_filename("call", "", "mp3")

        if self.call_url is None:
            pass
        elif exists(call_path):
            print(f"Found file {call_path}")
        else:
            bitrate = "32k"
            audio_secs = 10
            command = f'ffmpeg -i "{self.call_url}" -b:a {bitrate} -t {audio_secs} "{call_path}"'
            system(command)

    def cloze(self):
        return self.identify.replace(self.name, f"{{{{c1:{self.name}}}}}")


def get_page(url):
    html = requests.get(url).text
    return BeautifulSoup(html, "lxml")


def find_pages():
    base_url = "https://www.rspb.org.uk"
    bird_urls = []
    page_no = 1
    while True:
        page = get_page(base_url + f"/birds-and-wildlife/a-z?page={page_no}")
        print(base_url + f"/birds-and-wildlife/a-z?page={page_no}")
        urls = page.find(class_="cards").find_all("a")
        if not urls:
            break
        urls = [base_url + url["href"] for url in urls]
        print(urls)
        bird_urls += urls
        page_no += 1
    with open(BIRD_URLS, "w") as file:
        file.writelines([url + "\n" for url in bird_urls])


def get_info(url):
    page = get_page(url)

    name = page.find("h1").text

    binomial = page.find(class_="info latin").text

    group = page.find(string=re.compile("Group:"))
    group = re.compile("Group: (.*)").findall(group)[0]

    status = page.find(class_=re.compile(".* status")).text

    identify = page.find(class_="intro").text

    key_facts = json_spec(page)

    image_urls = [
        image.find("img")["src"]
        for image in page.find(class_="swiper swiper-gallery").find_all("rspb-image")
    ]

    try:
        call_url = get_audio_url(page.find("a", text="xeno-canto")["href"])
    except:
        call_url = None

    try:
        dist_url = page.find(attrs={"src": re.compile("distributionmap")})["src"]
    except:
        dist_url = None

    return Bird(
        [
            name,
            binomial,
            group,
            status,
            identify,
            key_facts,
            url,
            image_urls,
            call_url,
            dist_url,
        ]
    )


def get_audio_url(xeno_canto_url):
    page = get_page(xeno_canto_url)
    return "https:" + page.find(class_="xc-audio").contents[1]["data-xc-filepath"]


def random_bird():
    bird_urls = []
    with open(BIRD_URLS, "r") as file:
        bird_urls = [url.rstrip() for url in file.readlines()]
    return random.choice(bird_urls)


def random_test(times):
    birds = []
    for x in range(times):
        bird_url = random_bird()
        print(bird_url)
        bird = get_info(bird_url)
        birds.append(bird)
    return birds


def json_spec(page):
    """RSPB pages have some interactive information trapped in a big ball of
    enciphered JSON. Perform the relevant character replacements and return a
    small part of the JSON as a dictionary."""
    encrypt = page.find_all("script")[-1].text
    replacements = [
        ["{", "\n{"],
        ["}", "\n}"],
        ["&q;", '"'],
    ]
    for rep in replacements:
        encrypt = encrypt.replace(rep[0], rep[1])
    with open("contents.json", "w") as file:
        file.writelines(encrypt)
    reg = re.compile('\{.*?"slug":"general".*?\}', re.DOTALL)
    result = reg.search(encrypt).group()
    result = "\n".join(result.splitlines()[-3:]) + "}"
    return json.loads(result)["specifications"]


def normalize_csv(string):
    if string is None:
        return '""'
    doubled_quotes = string.replace('"', '""')
    return f'"{doubled_quotes}"'


def normalize_tag(string):
    string = string.replace(",", "")
    return string.replace(" ", "_")


def write_csv(filename, birds):
    birds.sort(key=lambda bird: bird.numbers())
    birds.reverse()
    with open(filename, "w") as file:
        file.writelines([str(bird) + "\n" for bird in birds])


def download_birds():
    birds = []
    bird_urls = []
    # The Slavonian Grebe, alas, has a broken page.
    skip = ["https://www.rspb.org.uk/birds-and-wildlife/slavonian-grebe"]
    with open(BIRD_URLS, "r") as file:
        bird_urls = [url.rstrip() for url in file.readlines()]
    for url in bird_urls:
        print(f"Fetching: {url}")
        if url in skip:
            continue
        bird = get_info(url)
        birds.append(bird)
        bird.download_media()
    write_csv(CSV_PATH, birds)
