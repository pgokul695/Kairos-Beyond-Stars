export const restaurants = [
  {
    id: 1,
    name: "Le Jardin Étoilé",
    image: "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800&auto=format&fit=crop",
    matchScore: 98,
    tags: ["French", "Fine Dining", "Romantic", "Michelin Star", "Quiet", "Luxury"],
    cuisine: "French",
    priceRange: "$$$$",
    rating: 4.8,
    reviews: 342,
    distance: 1.2,
    aiRecommended: true,
    location: {
      address: "123 Gourmet Avenue, Manhattan, NY 10001",
      lat: 40.7489,
      lng: -73.9680
    },
    aiSummary: "Le Jardin Étoilé perfectly matches your preference for elegant French cuisine with a romantic ambiance. The chef's innovative approach to classic dishes, combined with an extensive wine collection, makes it ideal for special occasions.",
    highlights: [
      "Michelin-starred chef with 15 years of experience",
      "Seasonal menu featuring local organic ingredients",
      "Private dining rooms available",
      "Award-winning wine cellar with 500+ selections"
    ],
    hours: "Tue-Sat: 5:30 PM - 10:30 PM, Closed Sun-Mon",
    gallery: [
      "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=800&auto=format&fit=crop"
    ],
    comparisonData: {
      ambiance: 95,
      service: 92,
      food: 98,
      value: 85,
      location: 90
    }
  },
  {
    id: 2,
    name: "Sakura Omakase",
    image: "https://images.unsplash.com/photo-1579584425555-c3ce17fd4351?w=800&auto=format&fit=crop",
    matchScore: 95,
    tags: ["Japanese", "Sushi", "Omakase", "Intimate", "Luxury"],
    cuisine: "Japanese",
    priceRange: "$$$$",
    rating: 4.9,
    reviews: 218,
    distance: 2.5,
    aiRecommended: true,
    location: {
      address: "456 Zen Street, Manhattan, NY 10002",
      lat: 40.7589,
      lng: -73.9780
    },
    aiSummary: "An intimate 12-seat omakase experience featuring the freshest fish flown daily from Tokyo's Tsukiji Market. The chef's artistry and attention to detail create an unforgettable culinary journey.",
    highlights: [
      "Chef trained at three-Michelin-starred restaurant in Tokyo",
      "Daily fish sourced from Tokyo markets",
      "Omakase-only dining experience",
      "Sake pairing curated by certified sommelier"
    ],
    hours: "Wed-Sun: 6:00 PM - 9:30 PM, Closed Mon-Tue",
    gallery: [
      "https://images.unsplash.com/photo-1579584425555-c3ce17fd4351?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1564489563601-c53cfc451e93?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1583623025817-d180a2221d0a?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=800&auto=format&fit=crop"
    ],
    comparisonData: {
      ambiance: 88,
      service: 95,
      food: 99,
      value: 82,
      location: 88
    }
  },
  {
    id: 3,
    name: "Trattoria Bella Vista",
    image: "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800&auto=format&fit=crop",
    matchScore: 92,
    tags: ["Italian", "Pasta", "Family-Friendly", "Wine Bar", "Budget-friendly"],
    cuisine: "Italian",
    priceRange: "$$$",
    rating: 4.7,
    reviews: 487,
    distance: 0.8,
    aiRecommended: true,
    location: {
      address: "789 Little Italy Lane, Brooklyn, NY 11201",
      lat: 40.7289,
      lng: -73.9580
    },
    aiSummary: "Authentic Italian cuisine in a warm, family-friendly atmosphere. The house-made pasta and wood-fired pizzas capture the essence of traditional Tuscan cooking.",
    highlights: [
      "All pasta made fresh daily in-house",
      "Traditional wood-fired brick oven",
      "Family recipes passed down three generations",
      "Extensive Italian wine list"
    ],
    hours: "Mon-Sun: 11:30 AM - 10:00 PM",
    gallery: [
      "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1595295333158-4742f28fbd85?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1551218372-a8789b81b253?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1544148103-0773bf10d330?w=800&auto=format&fit=crop"
    ],
    comparisonData: {
      ambiance: 85,
      service: 88,
      food: 92,
      value: 90,
      location: 85
    }
  },
  {
    id: 4,
    name: "Spice Route",
    image: "https://images.unsplash.com/photo-1585937421612-70a008356fbe?w=800&auto=format&fit=crop",
    matchScore: 89,
    tags: ["Indian", "Contemporary", "Vegetarian Options", "Fusion", "Budget-friendly"],
    cuisine: "Indian",
    priceRange: "$$",
    rating: 4.6,
    reviews: 325,
    distance: 3.2,
    aiRecommended: false,
    location: {
      address: "321 Curry Lane, Queens, NY 11354",
      lat: 40.7589,
      lng: -73.8280
    },
    aiSummary: "Modern Indian cuisine with creative twists on classic dishes. The chef combines traditional spices with contemporary techniques to create a unique dining experience.",
    highlights: [
      "Contemporary take on regional Indian cuisines",
      "Extensive vegetarian and vegan menu",
      "Craft cocktails with Indian-inspired flavors",
      "Tasting menu available"
    ],
    hours: "Tue-Sun: 12:00 PM - 10:00 PM, Closed Mon",
    gallery: [
      "https://images.unsplash.com/photo-1585937421612-70a008356fbe?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1567337710282-00832b415979?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1588166524941-3bf61a9c41db?w=800&auto=format&fit=crop"
    ],
    comparisonData: {
      ambiance: 82,
      service: 85,
      food: 90,
      value: 92,
      location: 78
    }
  },
  {
    id: 5,
    name: "The Golden Steakhouse",
    image: "https://images.unsplash.com/photo-1544025162-d76694265947?w=800&auto=format&fit=crop",
    matchScore: 94,
    tags: ["Steakhouse", "Premium Cuts", "Business Dining", "Wine", "Luxury"],
    cuisine: "American",
    priceRange: "$$$$",
    rating: 4.8,
    reviews: 412,
    distance: 1.5,
    aiRecommended: true,
    location: {
      address: "555 Prime Avenue, Manhattan, NY 10022",
      lat: 40.7689,
      lng: -73.9680
    },
    aiSummary: "A classic steakhouse featuring USDA Prime aged beef and an impressive wine collection. The sophisticated atmosphere makes it perfect for business dinners or celebrations.",
    highlights: [
      "Dry-aged USDA Prime beef for minimum 28 days",
      "Award-winning wine program with 1000+ bottles",
      "Private dining spaces for groups",
      "Classic steakhouse sides and seafood"
    ],
    hours: "Mon-Sun: 5:00 PM - 11:00 PM",
    gallery: [
      "https://images.unsplash.com/photo-1544025162-d76694265947?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1546964124-0cce460f38ef?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1558030006-450675393462?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1600891964092-4316c288032e?w=800&auto=format&fit=crop"
    ],
    comparisonData: {
      ambiance: 90,
      service: 93,
      food: 96,
      value: 84,
      location: 92
    }
  },
  {
    id: 6,
    name: "Ocean Pearl",
    image: "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=800&auto=format&fit=crop",
    matchScore: 91,
    tags: ["Seafood", "Contemporary", "Waterfront", "Sustainable", "Romantic"],
    cuisine: "Seafood",
    priceRange: "$$$",
    rating: 4.7,
    reviews: 298,
    distance: 2.1,
    aiRecommended: true,
    location: {
      address: "888 Harbor Drive, Brooklyn, NY 11231",
      lat: 40.6789,
      lng: -74.0180
    },
    aiSummary: "Stunning waterfront views complement the freshest sustainable seafood. The chef's commitment to ocean-to-table dining ensures every dish highlights the natural flavors of the sea.",
    highlights: [
      "Sustainably sourced seafood from local fishermen",
      "Waterfront dining with Manhattan skyline views",
      "Daily changing menu based on fresh catch",
      "Raw bar with oysters from coast to coast"
    ],
    hours: "Mon-Sun: 11:30 AM - 10:30 PM",
    gallery: [
      "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1528731500-c77d7d5c331e?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1615141982883-c7ad0e69fd62?w=800&auto=format&fit=crop",
      "https://images.unsplash.com/photo-1534604973900-c43ab4c2e0ab?w=800&auto=format&fit=crop"
    ],
    comparisonData: {
      ambiance: 93,
      service: 87,
      food: 91,
      value: 88,
      location: 95
    }
  }
];

export const cuisineTypes = [
  "French", "Japanese", "Italian", "Indian", "American", "Seafood", 
  "Chinese", "Thai", "Mexican", "Mediterranean"
];

export const dietaryPreferences = [
  "Vegetarian", "Vegan", "Gluten-Free", "Halal", "Kosher", "All"
];

export const priceRanges = [
  { label: "$", value: 1, description: "Under $15" },
  { label: "$$", value: 2, description: "$15-$30" },
  { label: "$$$", value: 3, description: "$31-$60" },
  { label: "$$$$", value: 4, description: "$60+" }
];
