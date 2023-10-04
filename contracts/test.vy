

WEEK: constant(uint256) = 604800 # One week in seconds
active_week: public(uint256)

@external
def update_week():
    """
    @dev 
        We know that Unix timestamp 0 began at 00:00 UTC on a Thursday
        We also take advantage of the fact that there are no decimals in uint type.
        Any remainder after division rounds down to nearest whole number.
    """
    if block.timestamp / WEEK > self.active_week:
        # We've advanced to the next week. Update active_week.
        self.active_week = block.timestamp / WEEK


