from obspy import read
import os
import argparse

def modify_miniseed_codes(input_file, output_file, new_network=None, new_station=None):
    """
    Modify network and/or station codes in a MiniSEED file.
    
    Parameters:
    -----------
    input_file : str
        Path to input MiniSEED file
    output_file : str
        Path to output MiniSEED file
    new_network : str, optional
        New network code (2 characters)
    new_station : str, optional
        New station code (up to 5 characters)
    
    Returns:
    --------
    bool
        True if successful, False otherwise
    """
    try:
        # Read the MiniSEED file
        st = read(input_file)
        
        # Check if any modifications are requested
        if not (new_network or new_station):
            print("No modifications requested")
            return False
            
        # Iterate through all traces in the stream
        for tr in st:
            if new_network:
                if len(new_network) != 2:
                    raise ValueError("Network code must be exactly 2 characters")
                tr.stats.network = new_network
                
            if new_station:
                if len(new_station) > 5:
                    raise ValueError("Station code cannot exceed 5 characters")
                tr.stats.station = new_station
                
        # Write the modified stream to a new file
        st.write(output_file, format='MSEED')
        print(f"Successfully modified {input_file} and saved to {output_file}")
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Modify network and station codes in a MiniSEED file')
    parser.add_argument('input_file', help='Input MiniSEED file path')
    parser.add_argument('output_file', help='Output MiniSEED file path')
    parser.add_argument('--network', '-n', help='New network code (2 characters)')
    parser.add_argument('--station', '-s', help='New station code (up to 5 characters)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input_file):
        print(f"Error: Input file {args.input_file} does not exist")
        return
        
    # Check if output directory exists
    output_dir = os.path.dirname(args.output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # Modify the file
    success = modify_miniseed_codes(
        args.input_file,
        args.output_file,
        args.network,
        args.station
    )
    
    if not success:
        print("Failed to modify MiniSEED file")

if __name__ == "__main__":
    main()