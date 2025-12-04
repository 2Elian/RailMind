from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class TrainInfo:
    train_no: str           # Train number
    start_station: str      # Starting station
    end_station: str        # Ending station
    arrival_time: str       # Arrival time (HH:MM)
    departure_time: str     # Departure time (HH:MM)
    waiting_hall: str       # Waiting hall
    ticket_gate: str        # Ticket gate
    platform: str           # Platform number

@dataclass
class OutputSchema:
    id: str
    question: str
    answer: str
    source_rows: List[int]
    question_type: str