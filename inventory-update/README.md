# Inventory Update

## Table of Contents
1. [Introduction](#introduction)
2. [Features](#features)
3. [Requirements](#requirements)
4. [Installation](#installation)
5. [Usage](#usage)
6. [Configuration](#configuration)
7. [Output](#output)
8. [State Preservation](#state-preservation)
9. [Troubleshooting](#troubleshooting)
10. [Contributing](#contributing)
11. [License](#license)

## Introduction

The Inventory Update is a Python script designed to automate the process of downloading, updating, and managing seismic station metadata from various FDSN (International Federation of Digital Seismograph Networks) web services. It provides a flexible and efficient way to maintain an up-to-date inventory of seismic stations, convert metadata formats, and merge XML files for further processing.

This tool is particularly useful for seismologists, geophysicists, and researchers working with large-scale seismic data from multiple networks.

## Features

- Download and update station metadata from multiple FDSN web services
- Support for processing specific networks or all available networks
- Convert FDSN StationXML to SeisComP XML format
- Merge SeisComP XML files for each network
- Detect and optionally add new stations to the inventory
- State preservation to resume interrupted processing
- Flexible command-line interface for easy integration into workflows

## Requirements

- Python 3.6 or higher
- ObsPy library
- `fdsnxml2inv` tool (part of the SeisComP software suite)
- `scxmlmerge` tool (part of the SeisComP software suite)

## Installation

1. Clone this repository:
   ```
   git@github.com:comoglu/miscellaneous-tools.git

   ```

2. Install the required Python packages:
   ```
   pip install obspy
   ```

3. Ensure that `fdsnxml2inv` and `scxmlmerge` are installed and available in your system PATH. These tools are part of the SeisComP software suite. If you haven't installed SeisComP, please follow the installation instructions on the [SeisComP website](https://www.seiscomp.de/doc/base/installation.html).

## Usage

The basic usage of the script is as follows:

```
python inventory_update.py <config_file> <output_dir> [options]
```

### Arguments:

- `config_file`: Path to the configuration XML file containing station information.
- `output_dir`: Directory to store the output files.

### Options:

- `--networks NETWORK [NETWORK ...]`: Specify one or more network codes to process. If not provided, all networks in the configuration file will be processed.
- `--state_file STATE_FILE`: Specify a custom state file to store processing progress (default: process_state.json).

### Examples:

1. Process all networks:
   ```
   python inventory_update.py config.xml /path/to/output
   ```

2. Process specific networks:
   ```
   python inventory_update.py config.xml /path/to/output --networks AU IU GE
   ```

3. Use a custom state file:
   ```
   python inventory_update.py config.xml /path/to/output --state_file my_custom_state.json
   ```

## Configuration

The script uses a configuration XML file to determine which stations to process. This file should follow the SeisComP3 schema. Here's a simple example of the structure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<seiscomp>
  <Config>
    <parameterSet>
      <parameter name="detecStream" value="BHZ"/>
      <parameter name="detecLocid" value=""/>
    </parameterSet>
    <parameterSet publicID="ParameterSet/trunk/Station/AU/ARMA">
      <parameter name="detecStream" value="BHZ"/>
      <parameter name="detecLocid" value=""/>
    </parameterSet>
    <!-- Add more stations as needed -->
  </Config>
</seiscomp>
```

## Output

The script generates the following outputs in the specified output directory:

1. FDSN StationXML files for each processed station.
2. SeisComP XML files converted from the FDSN StationXML files.
3. Merged SeisComP XML files for each network in the root of the output directory.

## State Preservation

The script uses a JSON file (default: `process_state.json`) to keep track of processed stations. This allows the script to resume from where it left off if interrupted. You can specify a custom state file using the `--state_file` option.

## Troubleshooting

- If you encounter issues with `fdsnxml2inv` or `scxmlmerge`, ensure that SeisComP is correctly installed and that these tools are available in your system PATH.
- For network-specific issues, check the FDSN web service status for the respective network.
- If you're having problems with a specific station, try processing it individually to isolate the issue.

## Contributing

Contributions to improve the Seismic Data Processor are welcome. Please feel free to submit issues, feature requests, or pull requests through GitHub.

## License

This project is open-source and available under the MIT License with an additional attribution requirement. See the [LICENSE](LICENSE) file for more details.


---

For more information or support, please open an issue on the GitHub repository.
