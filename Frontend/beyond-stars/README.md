# Beyond Stars - AI-Powered Dining Concierge

A modern, responsive web application that uses AI to help users discover their perfect dining experience. Built with React, Vite, and Tailwind CSS.

## 🌟 Features

### Pages

1. **Landing Page**
   - Hero section with dynamic background and stunning visuals
   - AI-powered search bar with smart suggestions
   - Feature highlights with hover effects
   - Call-to-action sections
   - Fully responsive design

2. **Results Page**
   - Restaurant cards with match scores, ratings, and tags
   - Interactive map view (sticky sidebar)
   - Advanced filtering (cuisine type, price, rating, distance)
   - Sort by match score or rating
   - Hover effects on restaurant cards

3. **Restaurant Detail Page**
   - Image gallery with thumbnail navigation
   - AI-generated summary and insights
   - Match score with visual indicators
   - Comparison chart showing ratings by category
   - Restaurant highlights and details
   - Action buttons (reservation, save, share)
   - Location map with directions

### Components

- **Navbar**: Responsive navigation with mobile menu
- **SearchBar**: AI-powered search with suggestions (hero and compact variants)
- **RestaurantCard**: Beautiful cards with images, ratings, and tags
- **MapView**: Interactive map visualization with location pins
- **ComparisonChart**: Visual breakdown of restaurant scores by category

## 🎨 Design Features

- **Warm Color Scheme**: Orange, cream, and dark tones
- **Modern UI Elements**:
  - Rounded corners and shadows
  - Gradients and glass-morphism effects
  - Smooth transitions and hover states
  - Animated elements
  - Responsive grid layouts

- **Professional Aesthetics**:
  - Clean, minimal design
  - Consistent spacing and typography
  - Visual hierarchy
  - Accessible color contrasts

## 🚀 Tech Stack

- **React 18**: Component-based UI
- **Vite**: Fast build tool and dev server
- **Tailwind CSS**: Utility-first CSS framework
- **React Router**: Client-side routing
- **Unsplash Images**: High-quality restaurant photos

## 📁 Project Structure

```
beyond-stars/
├── src/
│   ├── components/
│   │   ├── Navbar.jsx
│   │   ├── SearchBar.jsx
│   │   ├── RestaurantCard.jsx
│   │   ├── MapView.jsx
│   │   └── ComparisonChart.jsx
│   ├── pages/
│   │   ├── Home.jsx
│   │   ├── Results.jsx
│   │   └── RestaurantDetail.jsx
│   ├── data/
│   │   └── dummyData.js
│   ├── App.jsx
│   ├── main.jsx
│   └── index.css
├── tailwind.config.js
├── postcss.config.js
├── vite.config.js
└── package.json
```

## 🛠️ Installation & Setup

1. **Navigate to project directory**:
   ```bash
   cd beyond-stars
   ```

2. **Install dependencies** (already done):
   ```bash
   npm install
   ```

3. **Start development server**:
   ```bash
   npm run dev
   ```

4. **Open in browser**:
   Visit `http://localhost:5173`

## 📱 Responsive Design

The application is fully responsive and optimized for:
- Desktop (1920px+)
- Laptop (1024px - 1919px)
- Tablet (768px - 1023px)
- Mobile (320px - 767px)

## 🎯 Key Features Explained

### AI Match Score
Each restaurant has a match score (85-98%) that indicates how well it matches user preferences. The score is visually represented with:
- Color-coded badges (green for 95+, blue for 90-94, yellow/orange for 85-89)
- Prominent display on cards and detail pages

### Smart Search
The search bar features:
- AI-powered natural language processing
- Quick suggestions
- Dynamic placeholder text
- Animated focus states

### Interactive Map
The map view shows:
- Restaurant locations with colored pins
- Match score indicators
- Zoom and location controls
- Legend for score interpretation

### Comparison Charts
Visual analytics showing:
- Ambiance, Service, Food, Value, Location scores
- Animated progress bars
- Overall score calculation
- Category-specific emojis

## 🎨 Customization

### Colors
Primary colors can be customized in `tailwind.config.js`:
- Primary: Orange shades (#f97316 and variants)
- Cream: Yellow shades for accents
- Dark: Gray shades for text and backgrounds

### Content
Restaurant data is in `src/data/dummyData.js`:
- 6 sample restaurants with complete information
- Easily extensible for more entries
- Includes cuisine types and price ranges

## 🌐 Build for Production

```bash
npm run build
```

The build will be created in the `dist/` folder, ready for deployment.

## 🚀 Deployment

The app can be deployed to:
- Vercel
- Netlify
- GitHub Pages
- Any static hosting service

## 📝 Notes

- Node.js version: Currently running on v20.16.0 (Vite recommends v20.19+ but works fine)
- All images are from Unsplash (free, high-quality stock photos)
- The map is currently a placeholder - can be integrated with Google Maps, Mapbox, etc.

## 🎉 Features Highlights

✅ Modern, professional UI inspired by Airbnb and Michelin Guide
✅ Fully responsive design
✅ Smooth animations and transitions
✅ AI-themed branding and messaging
✅ Comprehensive restaurant information
✅ Visual data representation
✅ Easy navigation with React Router
✅ Accessible and SEO-friendly

## 📄 License

This project is for demonstration purposes.

---

Built with ❤️ using React, Vite, and Tailwind CSS
