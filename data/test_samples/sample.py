"""Sample Python module for parser testing."""

import os


class DataProcessor:
    """Processes incoming data records."""

    def __init__(self, source: str):
        self.source = source

    def process(self, records: list) -> list:
        """Apply transformations to each record."""
        return [self._transform(r) for r in records]

    def _transform(self, record):
        return str(record).strip()


def load_data(filepath: str) -> list:
    """Load raw data from a file."""
    with open(filepath) as fh:
        return fh.readlines()


def main():
    proc = DataProcessor("example")
    data = load_data("input.txt")
    result = proc.process(data)
    print(f"Processed {len(result)} records.")


if __name__ == "__main__":
    main()
