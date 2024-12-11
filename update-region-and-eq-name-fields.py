#!/usr/bin/env python

import sys
import math
import csv
from typing import List, Tuple, Optional
import seiscomp.core
import seiscomp.client
import seiscomp.datamodel as DM
import seiscomp.logging


class LocationReference:
    def __init__(self, name: str, state: str, country: str, lat: float, lon: float):
        self.name = name
        self.state = state
        self.country = country
        self.lat = lat
        self.lon = lon


class EventNaming(seiscomp.client.Application):
    def __init__(self, argc, argv):
        seiscomp.client.Application.__init__(self, argc, argv)
        self.setMessagingEnabled(True)
        self.setDatabaseEnabled(True, True)
        self.setDaemonEnabled(False)

        # Add event as primary messaging group
        self.setPrimaryMessagingGroup("EVENT")

        self.locations: List[LocationReference] = []

    def createCommandLineDescription(self):
        self.commandline().addGroup("Event")
        self.commandline().addStringOption(
            "Event", "eventID,E", "Event ID to process")
        self.commandline().addStringOption(
            "Event", "locations-file,L", "CSV file with reference locations")
        self.commandline().addOption(
            "Event", "test", "Test mode - no messages are sent")
        return True

    def validateParameters(self):
        if not super(EventNaming, self).validateParameters():
            return False

        try:
            self.locations_file = self.commandline().optionString("locations-file")
            print(f"Using locations file: {self.locations_file}")
        except:
            sys.stderr.write(
                "No locations file specified, use --locations-file\n")
            return False

        self.test = self.commandline().hasOption("test")
        return True

    def init(self):
        if not super(EventNaming, self).init():
            return False

        try:
            with open(self.locations_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        loc = LocationReference(
                            row['name'],
                            row['state'],
                            row['country'],
                            float(row['latitude']),
                            float(row['longitude'])
                        )
                        self.locations.append(loc)
                    except (KeyError, ValueError) as e:
                        sys.stderr.write(
                            f"Error parsing row: {row}, Error: {str(e)}\n")
                        continue

            print(f"Loaded {len(self.locations)} locations from file")
            if not self.locations:
                sys.stderr.write("No valid locations loaded from file\n")
                return False

        except Exception as e:
            sys.stderr.write(f"Error reading locations file: {str(e)}\n")
            return False

        return True

    def calculateDistance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
        """Calculate distance in km and bearing between two points"""
        try:
            lat1_rad = math.radians(lat1)
            lon1_rad = math.radians(lon1)
            lat2_rad = math.radians(lat2)
            lon2_rad = math.radians(lon2)

            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad
            a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * \
                math.cos(lat2_rad) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            distance = 6371 * c

            y = math.sin(dlon) * math.cos(lat2_rad)
            x = math.cos(lat1_rad) * math.sin(lat2_rad) - \
                math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon)
            bearing = math.degrees(math.atan2(y, x))
            bearing = (bearing + 360) % 360

            return distance, bearing
        except Exception as e:
            print(f"Error calculating distance: {e}")
            return float('inf'), 0

    def getDirectionString(self, bearing: float) -> str:
        """Convert bearing to cardinal direction"""
        dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        ix = round(bearing / (360 / len(dirs))) % len(dirs)
        return dirs[ix]

    def findClosestLocation(self, lat: float, lon: float) -> Optional[Tuple[LocationReference, float, str]]:
        """Find closest location and return (location, distance, direction)"""
        if not self.locations:
            return None

        closest = None
        min_distance = float('inf')
        closest_direction = ""

        print(f"Looking for closest location to {lat}, {lon}")

        for loc in self.locations:
            distance, bearing = self.calculateDistance(
                lat, lon, loc.lat, loc.lon)
            print(
                f"Checking {loc.name}: distance={distance:.1f}km, bearing={bearing:.1f}°")

            if distance < min_distance:
                min_distance = distance
                closest = loc
                closest_direction = self.getDirectionString(bearing)
                print(
                    f"New closest location: {loc.name} at {distance:.1f}km {closest_direction}")

        if closest:
            print(
                f"Final closest location: {closest.name} at {min_distance:.1f}km {closest_direction}")
            return closest, min_distance, closest_direction
        return None

    def updateEventDescriptions(self, event, region_name, location_name):
        """Update both region name and location-based name"""
        DM.Notifier.Enable()

        # Find existing descriptions
        region_desc = None
        location_desc = None
        existing_region_name = ""

        # Find existing descriptions
        for i in range(event.eventDescriptionCount()):
            desc = event.eventDescription(i)
            if desc.type() == DM.REGION_NAME:
                region_desc = desc
                existing_region_name = desc.text()
                # Remove any existing location info in parentheses
                if '(' in existing_region_name:
                    existing_region_name = existing_region_name.split('(')[
                        0].strip()
            elif desc.type() == DM.EARTHQUAKE_NAME:
                location_desc = desc

        # Handle region name - preserve existing name and append location info
        final_region_name = f"{existing_region_name or region_name} ({location_name})"

        if region_desc:
            if region_desc.text() != final_region_name:
                print(f"Updating region name to: {final_region_name}")
                region_desc.setText(final_region_name)
                DM.Notifier.Create(event, DM.OP_UPDATE, region_desc)
        else:
            print(f"Adding new region name: {final_region_name}")
            region_desc = DM.EventDescription()
            region_desc.setType(DM.REGION_NAME)
            region_desc.setText(final_region_name)
            event.add(region_desc)
            DM.Notifier.Create(event, DM.OP_ADD, region_desc)

        # Handle location name
        if location_desc:
            if location_desc.text() != location_name:
                print(f"Updating location name to: {location_name}")
                location_desc.setText(location_name)
                DM.Notifier.Create(event, DM.OP_UPDATE, location_desc)
        else:
            print(f"Adding new location name: {location_name}")
            location_desc = DM.EventDescription()
            location_desc.setType(DM.EARTHQUAKE_NAME)
            location_desc.setText(location_name)
            event.add(location_desc)
            DM.Notifier.Create(event, DM.OP_ADD, location_desc)

        # Update event
        event.creationInfo().setModificationTime(seiscomp.core.Time.GMT())
        DM.Notifier.Create("EventParameters", DM.OP_UPDATE, event)

        if not self.test:
            msg = DM.Notifier.GetMessage()
            if msg:
                self.connection().send(msg)
                print("Sent update notification")
        else:
            print("Test mode - no notification sent")

        DM.Notifier.Disable()

    def run(self):
        eventID = None
        try:
            eventID = self.commandline().optionString("eventID")
        except:
            pass

        if not eventID:
            sys.stderr.write("No event ID specified, use --eventID\n")
            return False

        print(f"Processing event: {eventID}")
        event = self.query().loadObject(DM.Event.TypeInfo(), eventID)
        if not event:
            sys.stderr.write(f"Event {eventID} not found\n")
            return False

        event = DM.Event.Cast(event)
        if not event:
            sys.stderr.write(f"Object {eventID} is not an event\n")
            return False

        # Load event descriptions
        self.query().loadEventDescriptions(event)

        # Load preferred origin
        org = None
        if event.preferredOriginID():
            print(f"Loading preferred origin: {event.preferredOriginID()}")
            org = self.query().loadObject(DM.Origin.TypeInfo(), event.preferredOriginID())
            org = DM.Origin.Cast(org)

            if org is None:
                print("Failed to load preferred origin")
                return False
        else:
            print("No preferred origin set for event")
            return False

        try:
            lat = org.latitude().value()
            lon = org.longitude().value()
            print(f"Event coordinates: {lat}, {lon}")
        except Exception as e:
            print(f"Failed to get coordinates: {e}")
            return False

        result = self.findClosestLocation(lat, lon)
        if not result:
            print("No closest location found")
            return False

        location, distance, direction = result
        distance_km = round(distance)

        # Generate names
        location_name = f"{distance_km} km {direction} of {location.name}"
        if location.state:
            location_name += f", {location.state}"
        if location.country:
            location_name += f", {location.country}"

        region_name = f"{location.name}, {location.state}, {location.country}"

        # Update descriptions
        self.updateEventDescriptions(event, region_name, location_name)
        return True


def main(argc, argv):
    app = EventNaming(argc, argv)
    return app()


if __name__ == "__main__":
    sys.exit(main(len(sys.argv), sys.argv))
