#!/usr/bin/python3

from obspy import read
import argparse
import sys

def txt_to_miniseed(input_file, output_file, network='IM', station='STKA'):
    try:
        # Read the input file using ObsPy's built-in reader
        stream = read(input_file)
        
        # Update network and station codes if provided
        for tr in stream:
            tr.stats.network = network
            tr.stats.station = station
        
        # Write to MiniSEED
        stream.write(output_file, format='MSEED')
        print(f"\nConverted {input_file} to {output_file}")
        print(f"Number of channels processed: {len(stream)}")
        
    except Exception as e:
        print(f"Error during conversion: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Convert text format to MiniSEED')
    parser.add_argument('input_file', help='Input text file')
    parser.add_argument('output_file', help='Output MiniSEED file')
    parser.add_argument('-n', '--network', default='IM', help='Network code (default: IM)')
    parser.add_argument('-s', '--station', default='STKA', help='Station code (default: STKA)')

    args = parser.parse_args()

    try:
        txt_to_miniseed(args.input_file, args.output_file, args.network, args.station)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()