import SearchBar from '../components/SearchBar';
import { Link } from 'react-router-dom';

const Home = () => {
  return (
    <div className="min-h-screen bg-gray-50">
      {/* Hero Section */}
      <div className="relative min-h-[600px] flex items-center justify-center overflow-hidden">
        {/* Background Image */}
        <div className="absolute inset-0 z-0">
          <img
            src="https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1600&auto=format&fit=crop"
            alt="Fine dining"
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-br from-gray-900/90 via-gray-900/70 to-primary-900/80"></div>
          
          {/* Animated Particles */}
          <div className="absolute inset-0 opacity-30">
            {[...Array(20)].map((_, i) => (
              <div
                key={i}
                className="absolute bg-white rounded-full animate-pulse"
                style={{
                  width: `${Math.random() * 4 + 1}px`,
                  height: `${Math.random() * 4 + 1}px`,
                  top: `${Math.random() * 100}%`,
                  left: `${Math.random() * 100}%`,
                  animationDelay: `${Math.random() * 3}s`,
                  animationDuration: `${Math.random() * 3 + 2}s`
                }}
              />
            ))}
          </div>
        </div>

        {/* Hero Content */}
        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center">
          <div className="mb-6">
            <div className="inline-flex items-center space-x-2 bg-white/10 backdrop-blur-md border border-white/20 rounded-full px-6 py-2 mb-8">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-white text-sm font-medium">AI-Powered Restaurant Discovery</span>
            </div>
          </div>

          <h1 className="text-5xl md:text-7xl font-bold mb-6">
            <span className="block text-white mb-2">Find Your Perfect</span>
            <span className="block bg-gradient-to-r from-primary-400 via-yellow-400 to-primary-400 bg-clip-text text-transparent">
              Dining Experience
            </span>
          </h1>

          <p className="text-xl md:text-2xl text-gray-200 mb-12 max-w-3xl mx-auto">
            Let AI guide you to restaurants that match your taste, mood, and preferences.
            No more endless scrolling—just perfect recommendations.
          </p>

          {/* Search Bar */}
          <div className="flex justify-center mb-8">
            <SearchBar variant="hero" />
          </div>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-8 max-w-2xl mx-auto mt-16">
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-bold text-white mb-1">1K+</div>
              <div className="text-sm text-gray-300"> Real Restaurants</div>
            </div>
            <div className="text-center border-x border-white/20">
              <div className="text-3xl md:text-4xl font-bold text-white mb-1">100ms</div>
              <div className="text-sm text-gray-300">Average Response Time</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-bold text-white mb-1">Data from+</div>
              <div className="text-sm text-gray-300">Zomato reviews (Bengaluru)</div>
            </div>
          </div>
        </div>

        {/* Scroll Indicator */}
        <div className="absolute bottom-8 left-1/2 transform -translate-x-1/2 animate-bounce">
          <svg
            className="w-6 h-6 text-white"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </div>
      </div>

      {/* CTA Section */}
      <div className="bg-gradient-to-r from-gray-900 via-primary-900 to-gray-900 py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">
            Ready to Discover Your Next Favorite Restaurant?
          </h2>
          <p className="text-xl text-gray-300 mb-10">
            Join thousands of food lovers who trust Beyond Stars for their dining decisions
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/results"
              className="bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white px-10 py-4 rounded-full font-semibold text-lg shadow-2xl hover:shadow-primary-500/50 transition-all duration-300 transform hover:scale-105"
            >
              Start Exploring
            </Link>
            <button className="bg-white/10 backdrop-blur-md hover:bg-white/20 text-white px-10 py-4 rounded-full font-semibold text-lg border-2 border-white/30 transition-all duration-300">
              Learn More
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;
