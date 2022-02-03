# test utime.time_ns()

try:
    import utime

    utime.sleep_us
    utime.time_ns
except (ImportError, AttributeError):
    print("SKIP")
    raise SystemExit


t0 = utime.time_ns()
utime.sleep_us(5000)
t1 = utime.time_ns()

# Check that time_ns increases.
print(t0 < t1)

# Check that time_ns counts correctly, but be very lenient with the bounds (2ms to 50ms).
if 2000000 < t1 - t0 < 50000000:
    print(True)
else:
    print(t0, t1, t1 - t0)
