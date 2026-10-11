"""Daily interesting historical facts and thoughts of the day for Khepri."""

from datetime import datetime
from typing import Optional

# Curated daily thoughts / philosophical wisdom
DAILY_THOUGHTS = [
    ("Simplicity is prerequisite for reliability.", "Edsger W. Dijkstra"),
    ("First, solve the problem. Then, write the code.", "John Johnson"),
    ("Focus on being productive instead of busy.", "Tim Ferriss"),
    ("The secret of getting ahead is getting started.", "Mark Twain"),
    ("Small daily improvements over time lead to stunning results.", "Robin Sharma"),
    ("Make it work, make it right, make it fast.", "Kent Beck"),
    ("Any fool can write code that a computer can understand. Good programmers write code that humans can understand.", "Martin Fowler"),
    ("Action is the foundational key to all success.", "Pablo Picasso"),
    ("Perfection is achieved not when there is nothing more to add, but when there is nothing left to take away.", "Antoine de Saint-Exupéry"),
    ("Do what you can, with what you have, where you are.", "Theodore Roosevelt"),
    ("Knowledge is of no value unless you put it into practice.", "Anton Chekhov"),
    ("You don't have to be great to start, but you have to start to be great.", "Zig Ziglar"),
    ("The best way to predict the future is to invent it.", "Alan Kay"),
    ("Discipline equals freedom.", "Jocko Willink"),
    ("Clarity of mind means clarity of passion.", "Blaise Pascal")
]

# Month-day specific historical & scientific milestones
MILESTONES = {
    (10, 11): "In 1968, Apollo 7 launched into Earth orbit—the first crewed mission in NASA's Apollo program, successfully testing the Command and Service Module in orbit.",
    (10, 12): "In 1999, the Day of Six Billion was observed, as the United Nations estimated Earth's human population had officially reached 6 billion people.",
    (10, 13): "In 1884, the Greenwich Meridian was adopted as the universal prime meridian (0° longitude) during the International Meridian Conference in Washington, D.C.",
    (10, 14): "In 1947, Chuck Yeager flew the Bell X-1 rocket plane past the speed of sound (Mach 1.06) in level flight, becoming the first human to break the sound barrier.",
    (10, 15): "In 1997, the Cassini-Huygens spacecraft was launched from Cape Canaveral to explore Saturn, its rings, and moons, operating for over 20 years in deep space.",
    (10, 16): "In 1923, Walt Disney and Roy O. Disney founded the Disney Brothers Cartoon Studio in Hollywood, California.",
    (10, 17): "In 1956, Queen Elizabeth II officially opened Calder Hall in the UK—the world's first commercial nuclear power station to deliver electricity into a public grid.",
    (10, 18): "In 1967, the Soviet space probe Venera 4 reached Venus, transmitting the first direct measurements of another planet's atmosphere.",
    (10, 19): "In 1987, world financial markets experienced 'Black Monday', leading to the adoption of circuit breakers and automated trading stops in modern computing.",
    (10, 20): "In 1973, the Sydney Opera House was formally opened by Queen Elizabeth II, renowned as one of the 20th century's distinctive architectural masterpieces."
}

# Generic fallback milestones for any calendar day
GENERIC_MILESTONES = [
    "In 1969, the first ARPANET message ('LO') was transmitted between UCLA and Stanford, establishing the foundation of the modern Internet.",
    "In 1977, the Voyager 1 spacecraft was launched; it is now the most distant human-made object from Earth in interstellar space.",
    "In 1983, the GNU Project was announced by Richard Stallman, initiating the free software movement and Unix-compatible operating system foundations.",
    "In 1990, Tim Berners-Lee wrote the first proposal for the World Wide Web, creating the first web browser and web server.",
    "In 1991, Linus Torvalds released the first public version (0.01) of the Linux kernel to an online newsgroup.",
    "In 2012, the Curiosity rover touched down in Gale Crater on Mars using a rocket-powered sky crane maneuver.",
    "In 2021, the James Webb Space Telescope completed deployment of its 6.5-meter gold-coated primary mirror in deep space."
]


def get_interesting_fact_today(dt: Optional[datetime] = None) -> str:
    """Return a notable historical or scientific milestone for today's date."""
    now = dt or datetime.now()
    key = (now.month, now.day)
    if key in MILESTONES:
        return MILESTONES[key]
    idx = (now.timetuple().tm_yday) % len(GENERIC_MILESTONES)
    return GENERIC_MILESTONES[idx]


def get_thought_of_the_day(dt: Optional[datetime] = None) -> str:
    """Return an inspiring quote and author for the day."""
    now = dt or datetime.now()
    idx = (now.timetuple().tm_yday) % len(DAILY_THOUGHTS)
    quote, author = DAILY_THOUGHTS[idx]
    return f'"{quote}" — *{author}*'
