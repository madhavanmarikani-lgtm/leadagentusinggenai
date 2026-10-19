"""ICP Configuration and Targeting Rules for B2B Lead Capture."""

from __future__ import annotations
import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# 5 ICP Pillars and intent keywords
ICP_CATEGORIES = {
    "AI Development": [
        "ai automation",
        "ai agent",
        "ai chatbot",
        "generative ai",
        "computer vision",
        "ai integration",
        "workflow automation",
        "ai implementation partner",
        "large language model",
        "llm",
    ],
    "Web and Mobile Development": [
        "mobile app launch",
        "custom software development",
        "web application",
        "mvp development",
        "product engineering",
        "app development partner",
        "platform modernization",
        "react native",
        "flutter",
        "full stack",
    ],
    "Dedicated Developers": [
        "engineering team expansion",
        "contract developers",
        "staff augmentation",
        "external development partner",
        "development outsourcing",
        "software delivery partner",
        "hire developers",
        "hire engineers",
        "software engineers",
    ],
    "Website and E-Commerce": [
        "website redesign",
        "e-commerce migration",
        "mobile commerce",
        "platform integration",
        "conversion optimization",
        "custom e-commerce development",
        "shopify",
        "magento",
        "woocommerce",
        "bigcommerce",
    ],
    "Agency Partnerships": [
        "white-label development",
        "white-label web development",
        "agency development partner",
        "outsourced development",
        "technical delivery partner",
        "digital agency",
        "creative agency",
    ],
}

# Target Regions
TARGET_REGIONS = {
    "US": {
        "names": ["united states", "usa", "u.s.", "u.s.a"],
        "phone_prefix": ["+1", "1-"],
        "top_states": [
            "california", "new york", "texas", "florida", "illinois",
            "massachusetts", "washington", "colorado", "austin", "san francisco",
        ],
    },
    "UK": {
        "names": ["united kingdom", "uk", "great britain", "england", "scotland"],
        "phone_prefix": ["+44", "020", "0161", "0121"],
        "top_cities": ["london", "manchester", "birmingham", "edinburgh", "leeds", "bristol"],
    },
}

# Target Company Size
COMPANY_SIZE_MIN = 50
COMPANY_SIZE_MAX = 200

# Target Industries
TARGET_INDUSTRIES = [
    "SaaS",
    "IT services",
    "e-commerce",
    "logistics",
    "healthcare",
    "education",
    "professional services",
]

# Target Decision Maker Titles
DECISION_MAKER_TITLES = [
    "Founder",
    "Co-Founder",
    "CEO",
    "Chief Executive Officer",
    "CTO",
    "Chief Technology Officer",
    "CIO",
    "Chief Information Officer",
    "COO",
    "Chief Operating Officer",
    "VP of Engineering",
    "Vice President of Engineering",
    "Head of Product",
    "Head of Engineering",
    "IT Director",
    "Agency Owner",
    "Managing Director",
]

# Ready-to-use discovery query templates targeted to 50-200 employees in US / UK
DISCOVERY_QUERY_TEMPLATES = {
    # 1. Agency Partnerships (White-Label Solutions)
    "agency_white_label_uk": '"digital agency" ("London" OR "Manchester") "our services" "team" -jobs -board -directory',
    "agency_white_label_us": '"digital agency" ("New York" OR "Texas" OR "California") "our services" "team" -jobs -board -directory',

    # 2. Companies Hiring Developers (Dedicated Developers / Staff Augmentation)
    "hiring_developers_us": 'SaaS ("New York" OR "Austin" OR "San Francisco") "we are hiring" "software engineer" "about us" -board -jobs',
    "hiring_developers_uk": 'SaaS ("London" OR "Manchester") "we are hiring" "software engineer" "about us" -board -jobs',

    # 3. Active Interest / Intent (AI Development, Web/Mobile, E-Commerce)
    "ai_development_us": 'SaaS ("New York" OR "Austin" OR "Boston") ("AI automation" OR "generative AI" OR "workflow automation") "about us"',
    "ai_development_uk": 'SaaS ("London" OR "Manchester") ("AI automation" OR "generative AI" OR "workflow automation") "about us"',
    "web_mobile_modernization": '("custom software development" OR "MVP development" OR "platform modernization") ("US" OR "UK") "contact us"',
    "ecommerce_redesign": '("Shopify Plus" OR "e-commerce migration" OR "website redesign") ("US" OR "UK") "our work"',
}

# Non-target locations to filter out
DISALLOWED_GEO_KEYWORDS = [
    "ontario", "toronto", "vancouver", "canada",
    "noida", "gurgaon", "bangalore", "mumbai", "delhi", "india",
    "sydney", "melbourne", "australia",
    "berlin", "munich", "germany",
    "paris", "france",
]
