#!/usr/bin/env python

import sys
import math
import csv
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from enum import Enum
import seiscomp.core
import seiscomp.client
import seiscomp.datamodel as DM
import seiscomp.logging
from seiscomp.seismology import Regions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('event_naming.log')
    ]
)
logger = logging.getLogger(__name__)


class DirectionType(Enum):
    CARDINAL = "cardinal"  # N, S, E, W
    INTERCARDINAL = "intercardinal"  # NE, SE, SW, NW
    DETAILED = "detailed"  # N, NNE, NE, ENE, etc.


@dataclass
class LocationReference:
    """Enhanced location reference with validation"""
    name: str
    state: str
    country: str
    lat: float
    lon: float
    population: Optional[int] = None

    def __post_init__(self):
        if not (-90 <= self.lat <= 90):
            raise ValueError(f"Invalid latitude: {self.lat}")
        if not (-180 <= self.lon <= 180):
            raise ValueError(f"Invalid longitude: {self.lon}")
        if not self.name:
            raise ValueError("Location name cannot be empty")

    def __str__(self):
        return f"{self.name}, {self.state}, {self.country}"


class LocationCache:
    """Cache for storing and managing location references"""

    def __init__(self):
        self._locations: Dict[str, LocationReference] = {}

    def add(self, location: LocationReference):
        key = f"{location.name}_{location.state}_{location.country}"
        self._locations[key] = location

    def get_all(self) -> List[LocationReference]:
        return list(self._locations.values())

    def clear(self):
        self._locations.clear()

    def size(self) -> int:
        return len(self._locations)


class EventNamingConfig:
    """Configuration container for event naming parameters"""

    def __init__(self):
        self.max_distance = 1000  # km
        self.min_population = 50000
        self.direction_type = DirectionType.DETAILED
        self.description_pattern = "{poi} {dist}km {dir}"
        self.Regions_enabled = True
        self.debug_mode = False
        self.show_state = True
        self.show_country = True

    @classmethod
    def from_config_file(cls, config_file: str) -> "EventNamingConfig":
        config = cls()
        try:
            with open(config_file, 'r') as f:
                # TODO: Implement config file parsing
                pass
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
        return config


class EventNaming(seiscomp.client.Application):
    def __init__(self, argc: int, argv: List[str]):
        seiscomp.client.Application.__init__(self, argc, argv)
        self.setMessagingEnabled(True)
        self.setDatabaseEnabled(True, True)
        self.setDaemonEnabled(False)
        self.setPrimaryMessagingGroup("EVENT")

        self.location_cache = LocationCache()
        self.config = EventNamingConfig()

    def createCommandLineDescription(self):
        """Create command line options"""
        self.commandline().addGroup("Event")
        self.commandline().addStringOption("Event", "eventID,E", "Event ID to process")
        self.commandline().addStringOption("Event", "locations-file,L",
                                           "CSV file with reference locations")
        self.commandline().addStringOption("Event", "direction-type,D",
                                           "Direction type (cardinal, intercardinal, detailed)")
        self.commandline().addIntOption("Event", "max-distance,M",
                                        "Maximum distance to consider (km)")
        self.commandline().addOption("Event", "test", "Test mode - no messages are sent")
        self.commandline().addOption("Event", "verbose,v", "Verbose output")
        return True

    def validateParameters(self):
        """Validate command line parameters"""
        if not super(EventNaming, self).validateParameters():
            return False

        try:
            # Handle direction type
            if self.commandline().hasOption("direction-type"):
                direction_str = self.commandline().optionString("direction-type").upper()
                self.config.direction_type = DirectionType[direction_str]

            # Handle max distance
            if self.commandline().hasOption("max-distance"):
                self.config.max_distance = self.commandline().optionInt("max-distance")
                if self.config.max_distance <= 0:
                    raise ValueError("Max distance must be positive")

            # Set debug mode
            if self.commandline().hasOption("verbose"):
                logger.setLevel(logging.DEBUG)
                self.config.debug_mode = True

            self.locations_file = self.commandline().optionString("locations-file")
            logger.info(f"Using locations file: {self.locations_file}")

        except Exception as e:
            logger.error(f"Parameter validation failed: {str(e)}")
            return False

        self.test = self.commandline().hasOption("test")
        return True

    def loadLocations(self) -> bool:
        """Load locations with enhanced error handling"""
        try:
            with open(self.locations_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                required_fields = {'name', 'state', 'country',
                                   'latitude', 'longitude', 'population'}
                if not required_fields.issubset(reader.fieldnames):
                    missing = required_fields - set(reader.fieldnames)
                    raise ValueError(f"Missing required fields: {missing}")

                for row_num, row in enumerate(reader, start=2):
                    try:
                        loc = LocationReference(
                            name=row['name'].strip(),
                            state=row['state'].strip(),
                            country=row['country'].strip(),
                            lat=float(row['latitude']),
                            lon=float(row['longitude']),
                            population=int(row.get('population', 0))
                        )
                        if loc.population >= self.config.min_population:
                            self.location_cache.add(loc)
                    except (ValueError, KeyError) as e:
                        logger.warning(
                            f"Skipping invalid row {row_num}: {str(e)}")
                        continue

            locations_count = self.location_cache.size()
            if locations_count == 0:
                raise ValueError("No valid locations loaded from file")

            logger.info(f"Successfully loaded {locations_count} locations")
            return True

        except Exception as e:
            logger.error(f"Failed to load locations: {str(e)}")
            return False

    def getDirectionString(self, bearing: float) -> str:
        """Enhanced direction string generator with multiple granularity levels"""
        # Normalize bearing to 0-360
        bearing = (bearing + 360) % 360

        if self.config.direction_type == DirectionType.CARDINAL:
            dirs = ["N", "E", "S", "W"]
            idx = int((bearing + 45) % 360 / 90)
            return dirs[idx]

        elif self.config.direction_type == DirectionType.INTERCARDINAL:
            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            idx = int((bearing + 22.5) % 360 / 45)
            return dirs[idx]

        else:  # DETAILED
            dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
            idx = int((bearing + 11.25) % 360 / 22.5)
            return dirs[idx]

    def calculateDistance(self, ref_lat: float, ref_lon: float,
                          event_lat: float, event_lon: float) -> Tuple[float, float]:
        """Calculate distance and bearing using Haversine formula"""
        try:
            R = 6371  # Earth radius in kilometers
            lat1, lon1 = map(math.radians, [ref_lat, ref_lon])
            lat2, lon2 = map(math.radians, [event_lat, event_lon])

            dlat = lat2 - lat1
            dlon = lon2 - lon1

            a = math.sin(dlat/2)**2 + math.cos(lat1) * \
                math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            distance = R * c

            # Calculate bearing
            y = math.sin(lon2 - lon1) * math.cos(lat2)
            x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * \
                math.cos(lat2) * math.cos(lon2 - lon1)
            bearing = math.degrees(math.atan2(y, x))
            bearing = (bearing + 360) % 360

            logger.debug(
                f"Distance calculation: {distance:.1f}km, bearing: {bearing:.1f}°")
            return distance, bearing

        except Exception as e:
            logger.error(f"Error in distance calculation: {e}")
            raise

    def findClosestLocation(self, event_lat: float, event_lon: float) -> Optional[Tuple[LocationReference, float, str]]:
        """Find closest location with enhanced filtering and validation"""
        locations = self.location_cache.get_all()
        if not locations:
            logger.error("No locations available")
            return None

        closest = None
        min_distance = float('inf')
        closest_bearing = 0

        logger.debug(f"Searching closest location to {event_lat}, {event_lon}")

        for loc in locations:
            try:
                distance, bearing = self.calculateDistance(
                    loc.lat, loc.lon, event_lat, event_lon)

                # Skip if beyond max distance
                if distance > self.config.max_distance:
                    continue

                if distance < min_distance:
                    min_distance = distance
                    closest = loc
                    closest_bearing = bearing
                    logger.debug(
                        f"New closest: {loc.name} at {distance:.1f}km")

            except Exception as e:
                logger.warning(
                    f"Error processing location {loc.name}: {str(e)}")
                continue

        if closest:
            direction = self.getDirectionString(closest_bearing)
            return closest, min_distance, direction

        logger.warning("No location found within maximum distance")
        return None

    def run(self):
        """Main processing function"""
        try:
            # Get event ID
            try:
                eventID = self.commandline().optionString("eventID")
            except Exception:
                logger.error("No event ID specified, use --eventID")
                return False

            # Load locations file
            try:
                locations_file = self.commandline().optionString("locations-file")
                if not self.loadLocations():
                    logger.error("Failed to load locations from file")
                    return False
            except Exception as e:
                logger.error(f"Error loading locations file: {e}")
                return False

            # Load event from database
            event = self.query().loadObject(DM.Event.TypeInfo(), eventID)
            if not event:
                logger.error(f"Event {eventID} not found in database")
                return False

            # Cast to Event type
            event = DM.Event.Cast(event)
            if not event:
                logger.error(f"Object {eventID} is not a valid event")
                return False

            # Load event descriptions
            try:
                self.query().loadEventDescriptions(event)
            except Exception as e:
                logger.warning(
                    f"Could not load existing event descriptions: {e}")

            # Get preferred origin ID
            if not event.preferredOriginID():
                logger.error("No preferred origin set for event")
                return False

            # Load preferred origin
            preferredOrigin = self.query().loadObject(
                DM.Origin.TypeInfo(), event.preferredOriginID())
            if not preferredOrigin:
                logger.error(
                    f"Preferred origin {event.preferredOriginID()} not found")
                return False

            # Cast to Origin type
            origin = DM.Origin.Cast(preferredOrigin)
            if not origin:
                logger.error("Invalid origin object")
                return False

            # Extract origin coordinates
            try:
                lat = origin.latitude().value()
                lon = origin.longitude().value()
                logger.info(f"Event coordinates: {lat}, {lon}")

                if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                    logger.error(f"Invalid coordinates: lat={lat}, lon={lon}")
                    return False

            except ValueError as e:
                logger.error(f"Error reading origin coordinates: {e}")
                return False

            # Find the closest city/location
            try:
                result = self.findClosestLocation(lat, lon)
                if not result:
                    # If no nearby city found, use region name only
                    region_name = Regions.getRegionName(lat, lon)
                    logger.info(
                        f"No nearby city found, using region: {region_name}")
                    if region_name:
                        return self.updateEventDescriptions(event, region_name, region_name)
                    else:
                        logger.error("Could not determine region name")
                        return False

                location, distance, direction = result
                distance_km = round(distance)

                # Format location name
                location_parts = []
                if location.name:
                    location_parts.append(location.name)
                if self.config.show_state and location.state:
                    location_parts.append(location.state)
                if self.config.show_country and location.country:
                    location_parts.append(location.country)

                base_location = ", ".join(location_parts)
                location_name = f"{distance_km} km {direction} of {base_location}"

                # Get region information
                region_name = Regions.getRegionName(lat, lon)
                if region_name:
                    region_name = f"{base_location} ({region_name})"
                else:
                    region_name = base_location

                logger.info(f"Generated location name: {location_name}")
                logger.info(f"Generated region name: {region_name}")

                # Update event descriptions in database
                if self.updateEventDescriptions(event, region_name, location_name):
                    logger.info("Successfully updated event descriptions")

                    # Add additional information as comment if configured
                    if self.config.debug_mode:
                        comment = (f"Location details: Distance={distance_km}km, "
                                   f"Direction={direction}, Coordinates={lat:.3f},{lon:.3f}")
                        self.addEventComment(event, comment)

                    return True
                else:
                    logger.error("Failed to update event descriptions")
                    return False

            except Exception as e:
                logger.error(f"Error processing event location: {e}")
                return False

        except Exception as e:
            logger.error(f"Unhandled error in main processing: {e}")
            return False

    def updateEventDescriptions(self, event: DM.Event, region_name: str, location_name: str) -> bool:
        """Update event descriptions in the database"""
        try:
            DM.Notifier.Enable()

            # Update region name description
            region_desc = None
            location_desc = None

            # Find existing descriptions
            for i in range(event.eventDescriptionCount()):
                desc = event.eventDescription(i)
                if desc.type() == DM.REGION_NAME:
                    region_desc = desc
                elif desc.type() == DM.EARTHQUAKE_NAME:
                    location_desc = desc

            # Update or create region name description
            if region_desc:
                if region_desc.text() != region_name:
                    logger.debug(f"Updating region name: {region_name}")
                    region_desc.setText(region_name)
                    DM.Notifier.Create(event, DM.OP_UPDATE, region_desc)
            else:
                logger.debug(f"Creating new region name: {region_name}")
                region_desc = DM.EventDescription()
                region_desc.setType(DM.REGION_NAME)
                region_desc.setText(region_name)
                event.add(region_desc)
                DM.Notifier.Create(event, DM.OP_ADD, region_desc)

            # Update or create location name description
            if location_desc:
                if location_desc.text() != location_name:
                    logger.debug(f"Updating location name: {location_name}")
                    location_desc.setText(location_name)
                    DM.Notifier.Create(event, DM.OP_UPDATE, location_desc)
            else:
                logger.debug(f"Creating new location name: {location_name}")
                location_desc = DM.EventDescription()
                location_desc.setType(DM.EARTHQUAKE_NAME)
                location_desc.setText(location_name)
                event.add(location_desc)
                DM.Notifier.Create(event, DM.OP_ADD, location_desc)

            # Send notifications unless in test mode
            if not self.test:
                msg = DM.Notifier.GetMessage()
                if msg:
                    self.connection().send(msg)
                    logger.info("Sent database update notification")
            else:
                logger.info("Test mode - no database updates sent")

            DM.Notifier.Disable()
            return True

        except Exception as e:
            logger.error(f"Error updating event descriptions: {e}")
            DM.Notifier.Disable()
            return False

    def addEventComment(self, event: DM.Event, comment: str, id: str = "EventNaming") -> bool:
        """Add a comment to the event"""
        try:
            commentObj = DM.Comment()
            commentObj.setId(id)
            commentObj.setText(comment)
            event.add(commentObj)

            if not self.test:
                DM.Notifier.Enable()
                # Correct way to create a notifier for the comment
                DM.Notifier.Create(event.publicID(), DM.OP_UPDATE, commentObj)
                msg = DM.Notifier.GetMessage()
                if msg:
                    self.connection().send(msg)
                DM.Notifier.Disable()

            logger.debug(f"Added event comment: {comment}")
            return True

        except Exception as e:
            logger.error(f"Error adding event comment: {e}")
            DM.Notifier.Disable()  # Make sure to disable notifier even if there's an error
            return False


def main():
    """Main entry point with enhanced error handling"""
    try:
        argv = sys.argv
        argc = len(argv)
        app = EventNaming(argc, argv)

        logger.info("Starting Event Naming application")
        result = app()

        if result:
            logger.info("Application completed successfully")
            return 0
        else:
            logger.error("Application failed")
            return 1

    except Exception as e:
        logger.critical(f"Critical application error: {e}")
        return 1


if __name__ == "__main__":
    # Example usage:
    # python event_naming.py -E eventID -L locations.csv --direction-type detailed --max-distance 1000 --verbose
    sys.exit(main())
