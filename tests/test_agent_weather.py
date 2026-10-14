import time
from pithon.agent.weather import extract_weather_location, is_weather_intent

def test_extract_weather_location():
    assert extract_weather_location("how is the weather in kolkata?") == "kolkata"
    assert extract_weather_location("what is the weather in New York today?") == "New York"
    assert extract_weather_location("temperature at San Francisco right now") == "San Francisco"
    assert extract_weather_location("weather for Tokyo") == "Tokyo"
    assert extract_weather_location("London weather") == "London"
    assert extract_weather_location("how is the weather?") == "Kolkata"

def test_extract_weather_location_redos_resilience():
    # Verify that repetitive uncontrolled input completes in milliseconds with no exponential/polynomial stalling
    long_input = "weather in " + "abc " * 200 + "xyz!"
    t0 = time.time()
    loc = extract_weather_location(long_input)
    duration = time.time() - t0
    assert duration < 0.1
    assert loc is not None
