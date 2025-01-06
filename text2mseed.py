from obspy import UTCDateTime, Trace, Stream
import numpy as np
import sys
import argparse
import base64
import struct


def calculate_checksum(data):
    """Calculate checksum for data validation"""
    try:
        # Use 32-bit integers for checksum calculation
        return sum(int(x) & 0xFFFFFFFF for x in data) & 0xFFFFFFFF
    except Exception as e:
        print(f"Error calculating checksum: {str(e)}")
        return None


def decode_cm6_data(encoded_data):
    """
    Decode CM6 format with corrected value ranges and unsigned conversion
    """
    try:
        # Remove any whitespace and newlines
        encoded_data = ''.join(encoded_data.split())

        # CM6 character set mapping
        cm6_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-"
        cm6_values = {char: i for i, char in enumerate(cm6_chars)}

        # Convert to bits
        bit_stream = ''
        for char in encoded_data:
            if char in cm6_values:
                bits = format(cm6_values[char], '06b')
                bit_stream += bits

        values = []
        prev_value = 0

        for i in range(0, len(bit_stream) - 15, 16):
            chunk = bit_stream[i:i+16]
            if len(chunk) == 16:
                value = int(chunk, 2)

                # Handle sign bit
                if value & 0x8000:
                    value = -(0x10000 - value)

                # Add to previous value (difference decoding)
                current_value = prev_value + value

                # Convert to unsigned by adding offset
                unsigned_value = current_value + 32768  # Offset to make values positive
                values.append(unsigned_value)
                prev_value = current_value

        return values
    except Exception as e:
        print(f"Error decoding CM6 data: {str(e)}")
        return []


def validate_sample_count(channels):
    """Validate sample counts across channels"""
    sample_counts = {chan: len(data['data'])
                     for chan, data in channels.items()}
    expected_count = 40 * 60 * 40  # 40 Hz * 60 seconds * 40 minutes

    print("\nSample Count Validation:")
    for channel, count in sample_counts.items():
        print(f"{channel}: {count} samples")
        if count != expected_count:
            print(
                f"Warning: {channel} has {count} samples, expected {expected_count}")

    # Check if all channels have the same number of samples
    if len(set(sample_counts.values())) > 1:
        print("Warning: Channels have different sample counts")

    return sample_counts


def txt_to_miniseed(input_file, output_file, network='IM', station='STKA'):
    # Read the input file
    with open(input_file, 'r') as f:
        lines = f.readlines()

    channels = {}
    current_channel = None
    current_data = []
    current_format = None
    checksums = {}

    # Process the file line by line
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith('WID2'):
            if current_channel and current_data:
                channels[current_channel]['data'] = current_data
                checksums[current_channel] = calculate_checksum(current_data)

            parts = line.split()
            channel_code = parts[4]
            format_type = parts[5]
            current_channel = channel_code
            current_format = format_type
            current_data = []

            channels[channel_code] = {
                'network': network,
                'station': station,
                'channel': channel_code,
                'format': format_type,
                'starttime': UTCDateTime(parts[1] + " " + parts[2]),
                'sampling_rate': float(parts[7]),
                'data': []
            }
        elif line.startswith('CHK2'):
            # Store checksum if provided in file
            if current_channel:
                try:
                    # Assuming hex format
                    checksum_value = int(line.split()[1], 16)
                    channels[current_channel]['expected_checksum'] = checksum_value
                except (IndexError, ValueError):
                    print(f"Warning: Invalid checksum format in line: {line}")
        elif line.startswith(('STA2', 'DAT2')):
            continue
        elif current_format == 'INT' and line[0].isdigit():
            values = list(map(int, line.split()))
            current_data.extend(values)
        elif current_format == 'CM6' and not line.startswith(('WID2', 'STA2', 'DAT2', 'CHK2')):
            decoded_values = decode_cm6_data(line)
            if decoded_values:
                current_data.extend(decoded_values)

    # Save the last channel's data and checksum
    if current_channel and current_data:
        channels[current_channel]['data'] = current_data
        checksums[current_channel] = calculate_checksum(current_data)

    # Validate sample counts
    validate_sample_count(channels)

    # Create a Stream object
    stream = Stream()

    # Process each channel
    for channel_code, channel_info in channels.items():
        if not channel_info['data']:
            print(f"Warning: No data for channel {channel_code}")
            continue

        data = np.array(channel_info['data'], dtype=np.int32)

        # Validation output
        print(f"\nValidation for {channel_code}:")
        print(f"Format: {channel_info['format']}")
        print(f"Number of samples: {len(data)}")
        print(f"Min value: {np.min(data)}")
        print(f"Max value: {np.max(data)}")
        print(f"Mean value: {np.mean(data)}")
        print(f"First few values: {data[:13]}")

        # Checksum validation
        calculated_checksum = checksums.get(channel_code)
        expected_checksum = channel_info.get('expected_checksum')
        if calculated_checksum is not None and expected_checksum is not None:
            print(f"Checksum validation for {channel_code}:")
            print(f"Calculated: {calculated_checksum:08X}")
            print(f"Expected:   {expected_checksum:08X}")
            if calculated_checksum != expected_checksum:
                print("Warning: Checksum mismatch!")

        stats = {
            'network': channel_info['network'],
            'station': channel_info['station'],
            'channel': channel_info['channel'],
            'starttime': channel_info['starttime'],
            'sampling_rate': channel_info['sampling_rate'],
            'mseed': {'dataquality': 'D'}
        }

        trace = Trace(data=data, header=stats)
        stream.append(trace)

    # Write to MiniSEED
    stream.write(output_file, format='MSEED', encoding='INT32', reclen=4096)

    print(f"\nConverted {input_file} to {output_file}")
    print(f"Number of channels processed: {len(channels)}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert text format to MiniSEED')
    parser.add_argument('input_file', help='Input text file')
    parser.add_argument('output_file', help='Output MiniSEED file')
    parser.add_argument('-n', '--network', default='IM',
                        help='Network code (default: IM)')
    parser.add_argument('-s', '--station', default='STKA',
                        help='Station code (default: STKA)')

    args = parser.parse_args()

    try:
        txt_to_miniseed(args.input_file, args.output_file,
                        args.network, args.station)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
