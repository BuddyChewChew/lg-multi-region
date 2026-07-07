import requests
import json
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
from xml.dom import minidom

USER_AGENT = 'Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 LG Browser/8.0.0 WebOS.TV-2024/04.00.00 (LG; OLED65C4PUA;)'

# Region -> language + output file prefix.
# Testing US, UK, and GB codes side by side since it's unconfirmed which
# code(s) the LG Channels API actually recognizes for the UK market.
REGIONS = {
    'US': {'language': 'en', 'prefix': 'lg_channels_us', 'epg_prefix': 'lg_epg_us'},
    'UK': {'language': 'en', 'prefix': 'lg_channels_uk', 'epg_prefix': 'lg_epg_uk'},
    'GB': {'language': 'en', 'prefix': 'lg_channels_gb', 'epg_prefix': 'lg_epg_gb'},
}

# Raw URL base used to build the x-tvg-url header in each M3U.
RAW_BASE_URL = "https://raw.githubusercontent.com/BuddyChewChew/lg-multi-region/refs/heads/main"

url = "https://api.lgchannels.com/api/v1.0/schedulelist"


def processar_regiao(country_code, config):
    language_code = config['language']
    m3u_filename = f"{config['prefix']}.m3u"
    xml_filename = f"{config['epg_prefix']}.xml"
    tvg_url = f"{RAW_BASE_URL}/{xml_filename}"

    # Horários em UTC calculados por região para garantir timestamps frescos
    # mesmo se o processamento de uma região anterior demorar.
    agora = datetime.now(timezone.utc)
    passado = agora - timedelta(hours=6)
    futuro = agora + timedelta(hours=12)
    start_time = passado.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_time = futuro.strftime('%Y-%m-%dT%H:%M:%SZ')

    params = {
        'region': country_code,
        'language': language_code,
        'startTime': start_time,
        'endTime': end_time
    }

    headers = {
        'User-Agent': USER_AGENT,
        'X-Device-Country': country_code,
        'X-Device-Language': language_code,
        'X-Authentication': 'lg-tv-services-key'
    }

    print(f"\n[{country_code}] Conectando à API da LG e baixando dados oficiais...")

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)

        if response.status_code != 200:
            print(f"[{country_code}] [ERRO] Falha na resposta da API: {response.status_code}")
            return

        dados = response.json()
        categorias = dados.get("categories", [])

        if not categorias:
            print(f"[{country_code}] [AVISO] API retornou 200 mas sem categorias/canais. Região pode não ser suportada.")
            return

        # ----------------------------------------------------
        # FASE 1: GERAR O ARQUIVO M3U (COM X-TVG-URL INJETADO)
        # ----------------------------------------------------
        total_canais = 0
        with open(m3u_filename, "w", encoding="utf-8") as f_m3u:
            f_m3u.write(f'#EXTM3U x-tvg-url="{tvg_url}"\n')

            for categoria in categorias:
                nome_categoria = categoria.get("categoryName", "General")

                for canal in categoria.get("channels", []):
                    channel_id = canal.get("channelId")
                    nome_canal = canal.get("channelName")
                    logo = canal.get("channelLogoUrl", "")
                    url_stream = canal.get("mediaStaticUrl", "")

                    if url_stream and channel_id:
                        url_limpa = url_stream.split('?')[0]
                        f_m3u.write(f'#EXTINF:-1 tvg-id="{channel_id}" tvg-logo="{logo}" group-title="{nome_categoria}",{nome_canal}\n')
                        f_m3u.write(f'{url_limpa}\n')
                        total_canais += 1

        print(f"[{country_code}] [SUCESSO] Lista '{m3u_filename}' gerada com {total_canais} canais mapeados.")

        # ----------------------------------------------------
        # FASE 2: GERAR O ARQUIVO XMLTV (EPG)
        # ----------------------------------------------------
        tv = ET.Element('tv', generator_info_name="LG Channels EPG Extractor")

        for categoria in categorias:
            for canal in categoria.get("channels", []):
                channel_id = canal.get("channelId")
                nome_canal = canal.get("channelName")

                if channel_id:
                    channel_node = ET.SubElement(tv, 'channel', id=channel_id)
                    display_name = ET.SubElement(channel_node, 'display-name')
                    display_name.text = nome_canal
                    if canal.get("channelLogoUrl"):
                        ET.SubElement(channel_node, 'icon', src=canal.get("channelLogoUrl"))

        total_programas = 0
        for categoria in categorias:
            for canal in categoria.get("channels", []):
                channel_id = canal.get("channelId")

                for programa in canal.get("programs", []):
                    prog_start = programa.get("startDateTime", "").replace("-", "").replace(":", "").replace("T", "").replace("Z", " +0000")
                    prog_end = programa.get("endDateTime", "").replace("-", "").replace(":", "").replace("T", "").replace("Z", " +0000")

                    titulo = (programa.get("programTitle") or "No Title").replace('&', '&amp;')
                    descricao = (programa.get("description") or "").replace('&', '&amp;')

                    if channel_id and prog_start and prog_end:
                        programme_node = ET.SubElement(tv, 'programme', start=prog_start, stop=prog_end, channel=channel_id)

                        title_node = ET.SubElement(programme_node, 'title', lang=language_code)
                        title_node.text = titulo

                        if descricao:
                            desc_node = ET.SubElement(programme_node, 'desc', lang=language_code)
                            desc_node.text = descricao

                        total_programas += 1

        xml_string = ET.tostring(tv, encoding='utf-8')
        reparsed = minidom.parseString(xml_string)
        xml_bonito = reparsed.toprettyxml(indent="  ")

        with open(xml_filename, "w", encoding="utf-8") as f_xml:
            f_xml.write(xml_bonito)

        print(f"[{country_code}] [SUCESSO] Guia de programação '{xml_filename}' gerado com {total_programas} programas reais da API!")

    except Exception as e:
        print(f"[{country_code}] [FALHA] Ocorreu um erro durante a execução: {e}")


if __name__ == "__main__":
    for country_code, config in REGIONS.items():
        processar_regiao(country_code, config)
