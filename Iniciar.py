import os
import requests
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom

COUNTRY_CODE = 'US'
LANGUAGE_CODE = 'en'
USER_AGENT = 'Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 LG Browser/8.0.0 WebOS.TV-2024/04.00.00 (LG; OLED65C4PUA;)'

M3U_FILENAME = "lg_channels_us.m3u"
EPG_FILENAME = "lg_epg_us.xml"

# GITHUB_REPOSITORY is auto-set by GitHub Actions as "owner/repo".
# Falling back to a placeholder lets the script still run locally,
# but the x-tvg-url header will only be correct when run via Actions.
GITHUB_REPOSITORY = os.environ.get('GITHUB_REPOSITORY', 'owner/repo')
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/refs/heads/main"
TVG_URL = f"{RAW_BASE_URL}/{EPG_FILENAME}"

# Time window in UTC
now = datetime.now(timezone.utc)
past = now - timedelta(hours=6)
future = now + timedelta(hours=12)

start_time = past.strftime('%Y-%m-%dT%H:%M:%SZ')
end_time = future.strftime('%Y-%m-%dT%H:%M:%SZ')

url = "https://api.lgchannels.com/api/v1.0/schedulelist"
params = {
    'region': COUNTRY_CODE,
    'language': LANGUAGE_CODE,
    'startTime': start_time,
    'endTime': end_time
}

headers = {
    'User-Agent': USER_AGENT,
    'X-Device-Country': COUNTRY_CODE,
    'X-Device-Language': LANGUAGE_CODE,
    'X-Authentication': 'lg-tv-services-key'
}

print("Connecting to the LG API and downloading official data...")

try:
    response = requests.get(url, headers=headers, params=params, timeout=15)

    if response.status_code == 200:
        data = response.json()

        # ----------------------------------------------------
        # PHASE 1: GENERATE THE M3U FILE (WITH X-TVG-URL INJECTED)
        # ----------------------------------------------------
        total_channels = 0
        with open(M3U_FILENAME, "w", encoding="utf-8") as f_m3u:
            f_m3u.write(f'#EXTM3U x-tvg-url="{TVG_URL}"\n')

            for category in data.get("categories", []):
                category_name = category.get("categoryName", "General")

                for channel in category.get("channels", []):
                    channel_id = channel.get("channelId")
                    channel_name = channel.get("channelName")
                    logo = channel.get("channelLogoUrl", "")
                    stream_url = channel.get("mediaStaticUrl", "")

                    if stream_url and channel_id:
                        clean_url = stream_url.split('?')[0]
                        f_m3u.write(f'#EXTINF:-1 tvg-id="{channel_id}" tvg-logo="{logo}" group-title="{category_name}",{channel_name}\n')
                        f_m3u.write(f'{clean_url}\n')
                        total_channels += 1

        print(f"[SUCCESS] '{M3U_FILENAME}' generated with {total_channels} channels mapped.")

        # ----------------------------------------------------
        # PHASE 2: GENERATE THE XMLTV FILE (EPG)
        # ----------------------------------------------------
        tv = ET.Element('tv', generator_info_name="LG Channels EPG Extractor")

        # Channel definitions
        for category in data.get("categories", []):
            for channel in category.get("channels", []):
                channel_id = channel.get("channelId")
                channel_name = channel.get("channelName")

                if channel_id:
                    channel_node = ET.SubElement(tv, 'channel', id=channel_id)
                    display_name = ET.SubElement(channel_node, 'display-name')
                    display_name.text = channel_name
                    if channel.get("channelLogoUrl"):
                        ET.SubElement(channel_node, 'icon', src=channel.get("channelLogoUrl"))

        # Programme listings
        total_programmes = 0
        for category in data.get("categories", []):
            for channel in category.get("channels", []):
                channel_id = channel.get("channelId")

                for programme in channel.get("programs", []):
                    prog_start = programme.get("startDateTime", "").replace("-", "").replace(":", "").replace("T", "").replace("Z", " +0000")
                    prog_end = programme.get("endDateTime", "").replace("-", "").replace(":", "").replace("T", "").replace("Z", " +0000")

                    title = (programme.get("programTitle") or "No Title").replace('&', '&amp;')
                    description = (programme.get("description") or "").replace('&', '&amp;')

                    if channel_id and prog_start and prog_end:
                        programme_node = ET.SubElement(tv, 'programme', start=prog_start, stop=prog_end, channel=channel_id)

                        title_node = ET.SubElement(programme_node, 'title', lang=LANGUAGE_CODE)
                        title_node.text = title

                        if description:
                            desc_node = ET.SubElement(programme_node, 'desc', lang=LANGUAGE_CODE)
                            desc_node.text = description

                        total_programmes += 1

        xml_string = ET.tostring(tv, encoding='utf-8')
        reparsed = minidom.parseString(xml_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")

        with open(EPG_FILENAME, "w", encoding="utf-8") as f_xml:
            f_xml.write(pretty_xml)

        print(f"[SUCCESS] EPG guide '{EPG_FILENAME}' generated with {total_programmes} real programmes from the API!")

    else:
        print(f"[ERROR] API request failed: {response.status_code}")

except Exception as e:
    print(f"[FAILURE] An error occurred during execution: {e}")
