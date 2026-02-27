import { Link } from 'react-router-dom';
import CircularProgress from './CircularProgress';
import AIBadge from './AIBadge';

const RestaurantCard = ({ restaurant, variant = 'default' }) => {
  const getMatchColor = (score) => {
    if (score >= 95) return 'from-green-500 to-emerald-500';
    if (score >= 90) return 'from-blue-500 to-cyan-500';
    if (score >= 85) return 'from-yellow-500 to-orange-500';
    return 'from-orange-500 to-red-500';
  };

  const getBadgeVariant = (score) => {
    if (score >= 95) return 'recommended';
    if (score >= 90) return 'topMatch';
    return null;
  };

  const badgeVariant = getBadgeVariant(restaurant.matchScore);

  return (
    <Link
      to={`/restaurant/${restaurant.id}`}
      className="group bg-white rounded-2xl overflow-hidden shadow-lg hover:shadow-2xl transition-all duration-300 transform hover:-translate-y-2 block"
    >
      {/* Image Container */}
      <div className="relative h-56 overflow-hidden">
        <img
          src={restaurant.image}
          alt={restaurant.name}
          className="w-full h-full object-cover transform group-hover:scale-110 transition-transform duration-500"
        />
        
        {/* AI Recommendation Badge */}
        {badgeVariant && (
          <div className="absolute top-4 left-4 z-10">
            <AIBadge variant={badgeVariant} />
          </div>
        )}

        {/* Circular Progress Badge */}
        {variant === 'grid' && (
          <div className="absolute top-4 right-4">
            <div className="bg-white/95 backdrop-blur-md rounded-2xl p-2 shadow-xl">
              <CircularProgress value={restaurant.matchScore} size={80} strokeWidth={6} label="Match" />
            </div>
          </div>
        )}

        {/* Standard Match Score Badge (for list view) */}
        {variant === 'default' && (
          <div className="absolute top-4 right-4">
            <div className={`relative bg-gradient-to-br ${getMatchColor(restaurant.matchScore)} p-1 rounded-2xl shadow-lg`}>
              <div className="bg-white px-4 py-2 rounded-xl">
                <div className="text-center">
                  <div className="text-2xl font-bold bg-gradient-to-br from-gray-800 to-gray-600 bg-clip-text text-transparent">
                    {restaurant.matchScore}%
                  </div>
                  <div className="text-xs text-gray-600 font-medium -mt-1">Match</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Price Range Badge */}
        <div className="absolute top-4 left-4 bg-black/60 backdrop-blur-md text-white px-3 py-1 rounded-full text-sm font-semibold">
          {restaurant.priceRange}
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {/* Title and Rating */}
        <div className="mb-3">
          <h3 className="text-xl font-bold text-gray-900 mb-2 group-hover:text-primary-600 transition-colors">
            {restaurant.name}
          </h3>
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-1">
              {[...Array(5)].map((_, i) => (
                <svg
                  key={i}
                  className={`w-4 h-4 ${
                    i < Math.floor(restaurant.rating)
                      ? 'text-yellow-400'
                      : 'text-gray-300'
                  }`}
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                </svg>
              ))}
            </div>
            <span className="text-sm text-gray-600">
              {restaurant.rating} ({restaurant.reviews} reviews)
            </span>
          </div>
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-2 mb-4">
          {restaurant.tags.slice(0, 3).map((tag, index) => (
            <span
              key={index}
              className="bg-gradient-to-r from-primary-50 to-yellow-50 text-primary-700 px-3 py-1 rounded-full text-xs font-medium border border-primary-200"
            >
              {tag}
            </span>
          ))}
          {restaurant.tags.length > 3 && (
            <span className="bg-gray-100 text-gray-600 px-3 py-1 rounded-full text-xs font-medium">
              +{restaurant.tags.length - 3}
            </span>
          )}
        </div>

        {/* AI Summary Preview */}
        <p className="text-gray-600 text-sm line-clamp-2 mb-4">
          {restaurant.aiSummary}
        </p>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-gray-100">
          <div className="flex items-center text-gray-500 text-sm">
            <svg
              className="w-4 h-4 mr-1"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            <span className="truncate">{restaurant.cuisine}</span>
          </div>
          <div className="flex items-center text-primary-600 font-semibold text-sm group-hover:text-primary-700">
            <span>View Details</span>
            <svg
              className="w-4 h-4 ml-1 transform group-hover:translate-x-1 transition-transform"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5l7 7-7 7"
              />
            </svg>
          </div>
        </div>
      </div>
    </Link>
  );
};

export default RestaurantCard;
