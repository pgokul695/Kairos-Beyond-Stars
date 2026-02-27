const MapView = ({ restaurants, selectedRestaurant }) => {
  return (
    <div className="h-full bg-gradient-to-br from-gray-100 to-gray-200 rounded-2xl overflow-hidden shadow-xl sticky top-20">
      <div className="relative h-full">
        {/* Map Placeholder */}
        <div className="absolute inset-0 flex items-center justify-center bg-gray-800">
          <div className="text-center p-8">
            <div className="bg-gradient-to-br from-primary-500 to-yellow-500 p-4 rounded-full inline-block mb-4">
              <svg
                className="w-12 h-12 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"
                />
              </svg>
            </div>
            <h3 className="text-white text-xl font-bold mb-2">Interactive Map View</h3>
            <p className="text-gray-300 text-sm mb-6">
              Showing {restaurants.length} restaurants in your area
            </p>
            
            {/* Simulated Map Pins */}
            <div className="grid grid-cols-2 gap-4 mt-6">
              {restaurants.slice(0, 6).map((restaurant, index) => (
                <div
                  key={restaurant.id}
                  className={`bg-white/10 backdrop-blur-md rounded-lg p-3 border-2 transition-all cursor-pointer ${
                    selectedRestaurant?.id === restaurant.id
                      ? 'border-primary-400 scale-105'
                      : 'border-white/20 hover:border-white/40'
                  }`}
                >
                  <div className="flex items-center space-x-2">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center bg-gradient-to-br ${
                      restaurant.matchScore >= 95
                        ? 'from-green-500 to-emerald-500'
                        : restaurant.matchScore >= 90
                        ? 'from-blue-500 to-cyan-500'
                        : 'from-yellow-500 to-orange-500'
                    }`}>
                      <svg
                        className="w-4 h-4 text-white"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </div>
                    <div className="flex-1 text-left">
                      <div className="text-white text-xs font-semibold truncate">
                        {restaurant.name}
                      </div>
                      <div className="text-gray-300 text-xs">{restaurant.matchScore}% match</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Map Controls */}
        <div className="absolute top-4 right-4 flex flex-col space-y-2">
          <button className="bg-white hover:bg-gray-50 p-3 rounded-lg shadow-lg transition-colors">
            <svg
              className="w-5 h-5 text-gray-700"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 6v6m0 0v6m0-6h6m-6 0H6"
              />
            </svg>
          </button>
          <button className="bg-white hover:bg-gray-50 p-3 rounded-lg shadow-lg transition-colors">
            <svg
              className="w-5 h-5 text-gray-700"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M20 12H4"
              />
            </svg>
          </button>
        </div>

        {/* Location Button */}
        <div className="absolute bottom-4 right-4">
          <button className="bg-white hover:bg-gray-50 p-3 rounded-full shadow-lg transition-colors group">
            <svg
              className="w-6 h-6 text-gray-700 group-hover:text-primary-600 transition-colors"
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
          </button>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 left-4 bg-white/95 backdrop-blur-md rounded-lg p-3 shadow-lg">
          <div className="text-xs font-semibold text-gray-700 mb-2">Match Score</div>
          <div className="space-y-1">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 rounded-full bg-gradient-to-br from-green-500 to-emerald-500"></div>
              <span className="text-xs text-gray-600">95%+</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 rounded-full bg-gradient-to-br from-blue-500 to-cyan-500"></div>
              <span className="text-xs text-gray-600">90-94%</span>
            </div>
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 rounded-full bg-gradient-to-br from-yellow-500 to-orange-500"></div>
              <span className="text-xs text-gray-600">85-89%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MapView;
