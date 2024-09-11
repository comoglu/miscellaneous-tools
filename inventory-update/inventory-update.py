import os
import subprocess
import argparse
import hashlib
import json
from collections import defaultdict
import xml.etree.ElementTree as ET
from obspy.clients.fdsn import Client
from obspy import UTCDateTime

START_DATE = UTCDateTime("2010-01-01")
NETWORKS_TO_CHECK_NEW_STATIONS = ["2O", "3B", "AF", "AU", "IU", "II", "G", "GE", "IA", "JP", "IC", "IO"]

def get_client(network):
    fdsn_sources = {
        "http://auspass.edu.au:80": ["M8", "S1"],
        "https://data.raspberryshake.org": ["AM"],
        "http://geofon.gfz-potsdam.de": ["GE"],
        "https://geof.bmkg.go.id": ["IA"],
        "http://seisrequest.iag.usp.br": ["BL", "BR"],
        "http://seis-pub.ga.gov.au:8081": ["AU", "2O", "3B", "YW"],
        "https://service.iris.edu": ["AF", "AI", "AK", "AT", "BK", "BL", "C", "C1", "CM", "CN", "CU", "EC", "EI", "GB", "GI", "GT", "HK", "HV", "IC", "II", "IM", "IN", "IO", "IU", "JP", "KG", "KZ", "MI", "MM", "MX", "MY", "NK", "NN", "NO", "ON", "OV", "PB", "PL", "PM", "PS", "PT", "RM", "TC", "TM", "TW", "US", "UW", "VU", "YC"],
        "http://webservices.ingv.it": ["MN"],
        "https://service.geonet.org.nz": ["NZ"],
        "http://ws.resif.fr": ["G", "ND"]
    }
    
    for base_url, networks in fdsn_sources.items():
        if network in networks:
            return Client(base_url)
    
    print(f"Warning: No specific FDSN source found for network {network}. Using IRIS as default.")
    return Client("IRIS")

def parse_config_xml(config_file):
    tree = ET.parse(config_file)
    root = tree.getroot()
    
    stations = []
    namespace = {'sc': 'http://geofon.gfz-potsdam.de/ns/seiscomp3-schema/0.12'}
    
    for parameterSet in root.findall('.//sc:parameterSet', namespace):
        publicID = parameterSet.get('publicID', '')
        if publicID.startswith('ParameterSet/trunk/Station/'):
            parts = publicID.split('/')
            if len(parts) >= 5:
                network = parts[3]
                station = parts[4]
                detecStream = None
                detecLocid = ""
                
                for param in parameterSet.findall('.//sc:parameter', namespace):
                    name_elem = param.find('sc:name', namespace)
                    value_elem = param.find('sc:value', namespace)
                    
                    if name_elem is not None and value_elem is not None:
                        name = name_elem.text
                        value = value_elem.text
                        if name == 'detecStream':
                            detecStream = value if value else None
                        elif name == 'detecLocid':
                            detecLocid = value if value else ""
                
                stations.append({
                    "network": network,
                    "station": station,
                    "detecStream": detecStream,
                    "detecLocid": detecLocid
                })
    
    return stations

def get_file_hash(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def process_station(station_info, output_dir, reference_time):
    network_code = station_info["network"]
    station_code = station_info["station"]
    client = get_client(network_code)

    try:
        station_dir = os.path.join(output_dir, network_code, station_code)
        os.makedirs(station_dir, exist_ok=True)

        xml_file = os.path.join(station_dir, f"{network_code}.{station_code}.xml")
        old_hash = get_file_hash(xml_file) if os.path.exists(xml_file) else None

        try:
            # First attempt with includerestricted=True
            updated_inv = client.get_stations(network=network_code, station=station_code, 
                                              starttime=START_DATE,
                                              endtime=reference_time,
                                              level="response",
                                              includerestricted=True)
        except Exception as e:
            if "includerestricted" in str(e).lower():
                # If 'includerestricted' is not supported, try without it
                print(f"Server for {network_code} doesn't support 'includerestricted'. Retrying without it.")
                updated_inv = client.get_stations(network=network_code, station=station_code, 
                                                  starttime=START_DATE,
                                                  endtime=reference_time,
                                                  level="response")
            else:
                # If it's a different error, re-raise it
                raise

        if not updated_inv:
            print(f"No data available for station {station_code} in network {network_code}")
            return False

        updated_inv.write(xml_file, format="STATIONXML")
        new_hash = get_file_hash(xml_file)

        if old_hash != new_hash:
            print(f"Updated inventory saved for station {station_code} in network {network_code}")
            return True
        else:
            print(f"No changes in inventory for station {station_code} in network {network_code}")
            return False

    except Exception as e:
        print(f"Error processing station {station_code} in network {network_code}: {str(e)}")
        return False

def get_network_stations(client, network, reference_time):
    try:
        inventory = client.get_stations(network=network, 
                                        starttime=START_DATE,
                                        endtime=reference_time,
                                        level="station",
                                        includerestricted=True)
        return set(station.code for station in inventory[0].stations)
    except Exception as e:
        print(f"Error getting stations for network {network}: {str(e)}")
        return set()

def detect_new_stations(config_stations, fdsn_stations):
    return fdsn_stations - config_stations

def convert_to_seiscomp_xml(fdsn_xml_file, seiscomp_xml_file):
    try:
        subprocess.run(["fdsnxml2inv", fdsn_xml_file, seiscomp_xml_file], check=True)
        print(f"Converted {fdsn_xml_file} to SeisComP XML format: {seiscomp_xml_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting {fdsn_xml_file} to SeisComP XML: {e}")
    except FileNotFoundError:
        print("fdsnxml2inv not found. Please ensure it's installed and in your PATH.")

def convert_xml_files(output_dir, networks=None):
    for root, dirs, files in os.walk(output_dir):
        network = os.path.basename(root)
        if networks and network not in networks:
            continue
        for file in files:
            if file.endswith(".xml") and not file.startswith("seiscomp_"):
                fdsn_xml_file = os.path.join(root, file)
                seiscomp_xml_file = os.path.join(root, f"seiscomp_{file}")
                convert_to_seiscomp_xml(fdsn_xml_file, seiscomp_xml_file)

def merge_seiscomp_xmls(output_dir, networks=None):
    for network_dir in os.listdir(output_dir):
        if networks and network_dir not in networks:
            continue
        network_path = os.path.join(output_dir, network_dir)
        if os.path.isdir(network_path):
            xml_files = []
            for root, dirs, files in os.walk(network_path):
                for file in files:
                    if file.startswith("seiscomp_") and file.endswith(".xml"):
                        xml_files.append(os.path.join(root, file))
            
            if xml_files:
                output_file = os.path.join(output_dir, f"{network_dir}.xml")
                
                try:
                    merge_command = ["scxmlmerge"] + xml_files
                    
                    with open(output_file, 'w') as outfile:
                        subprocess.run(merge_command, stdout=outfile, check=True)
                    
                    print(f"Successfully merged XML files for network {network_dir}")
                    
                    for xml_file in xml_files:
                        os.remove(xml_file)
                    print(f"Removed individual XML files for network {network_dir}")
                    
                except subprocess.CalledProcessError as e:
                    print(f"Error merging XML files for network {network_dir}: {e}")
                except Exception as e:
                    print(f"Unexpected error for network {network_dir}: {e}")
            else:
                print(f"No SeisComP XML files found for network {network_dir}")

def save_state(state_file, processed_stations):
    with open(state_file, 'w') as f:
        json.dump(list(processed_stations), f)

def load_state(state_file):
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            return set(tuple(item) for item in json.load(f))
    return set()

def update_station_inventory(config_file, output_dir, reference_time, networks_to_process, state_file):
    stations = parse_config_xml(config_file)
    updated_stations = []
    failed_stations = []
    new_stations_by_network = defaultdict(set)

    processed_stations = load_state(state_file)
    config_stations_by_network = defaultdict(set)

    for station_info in stations:
        network = station_info['network']
        station = station_info['station']
        
        if networks_to_process and network not in networks_to_process:
            continue

        config_stations_by_network[network].add(station)

        station_key = (network, station)
        if station_key not in processed_stations:
            if process_station(station_info, output_dir, reference_time):
                updated_stations.append(station_info)
            else:
                failed_stations.append(station_info)
            processed_stations.add(station_key)
            save_state(state_file, processed_stations)

    for network in (networks_to_process or NETWORKS_TO_CHECK_NEW_STATIONS):
        if network in config_stations_by_network:
            client = get_client(network)
            fdsn_stations = get_network_stations(client, network, reference_time)
            new_stations = detect_new_stations(config_stations_by_network[network], fdsn_stations)
            if new_stations:
                new_stations_by_network[network] = new_stations

    print(f"\nUpdated {len(updated_stations)} stations.")
    if failed_stations:
        print(f"Failed to update {len(failed_stations)} stations:")
        for station in failed_stations:
            print(f"  Network: {station['network']}, Station: {station['station']}")

    if new_stations_by_network:
        print("\nNew stations detected:")
        for network, stations in new_stations_by_network.items():
            print(f"  Network {network}: {', '.join(sorted(stations))}")
        
        user_input = input("Do you want to add these new stations to the inventory? (yes/no): ").lower()
        if user_input == 'yes':
            for network, stations in new_stations_by_network.items():
                for station in stations:
                    station_info = {"network": network, "station": station, "detecStream": None, "detecLocid": ""}
                    if process_station(station_info, output_dir, reference_time):
                        updated_stations.append(station_info)
                    else:
                        failed_stations.append(station_info)
                    processed_stations.add((network, station))
                    save_state(state_file, processed_stations)

    user_input = input("\nDo you want to convert updated FDSNXML files to SeisComP XML? (yes/no): ").lower()
    if user_input == 'yes':
        convert_xml_files(output_dir, networks_to_process)
        merge_seiscomp_xmls(output_dir, networks_to_process)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update and merge SeisComP XML files")
    parser.add_argument("config_file", help="Path to the config.xml file")
    parser.add_argument("output_dir", help="Directory to store output files")
    parser.add_argument("--networks", nargs='+', help="Specific networks to process (optional)")
    parser.add_argument("--state_file", default="process_state.json", help="File to store processing state (default: process_state.json)")
    args = parser.parse_args()

    reference_time = UTCDateTime.now()
    update_station_inventory(args.config_file, args.output_dir, reference_time, args.networks, args.state_file)
