import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const SearchBar = ({ variant = 'default' }) => {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const navigate = useNavigate();

  const handleSearch = (e) => {
    e.preventDefault();
    if (query.trim()) {
      navigate('/results', { state: { searchQuery: query } });
    }
  };

  const isHero = variant === 'hero';

  return (
    <form onSubmit={handleSearch} className={`w-full ${isHero ? 'max-w-4xl' : 'max-w-2xl'}`}>
      <div
        className={`relative ${
          isHero
            ? 'bg-white/95 backdrop-blur-md'
            : 'bg-white'
        } rounded-2xl shadow-2xl transition-all duration-300 ${
          focused ? 'ring-4 ring-primary-400/50 scale-[1.02]' : 'hover:shadow-primary-500/20'
        }`}
      >
        <div className="flex items-center p-2">
          {/* AI Icon */}
          <div className="flex items-center justify-center w-12 h-12 bg-gradient-to-br from-primary-500 to-yellow-500 rounded-xl ml-2 flex-shrink-0">
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
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
          </div>

          {/* Input */}
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            placeholder="Tell AI what you're craving... 'romantic Italian with great wine' or 'best sushi in town'"
            className={`flex-1 px-4 py-3 ${
              isHero ? 'text-lg' : 'text-base'
            } text-gray-800 placeholder-gray-400 bg-transparent border-none focus:outline-none`}
          />

          {/* Search Button */}
          <button
            type="submit"
            className="bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white px-8 py-3 rounded-xl font-semibold shadow-lg hover:shadow-primary-500/50 transition-all duration-300 transform hover:scale-105 flex items-center space-x-2 flex-shrink-0 mr-2"
          >
            <span>Search</span>
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          </button>
        </div>

        {/* AI Suggestions */}
        {isHero && (
          <div className="px-4 pb-3 flex flex-wrap gap-2">
            <span className="text-xs text-gray-500 font-medium">Try:</span>
            {['Fine dining near me', 'Vegan brunch spots', 'Date night restaurants'].map(
              (suggestion, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setQuery(suggestion)}
                  className="text-xs bg-gray-100 hover:bg-primary-50 text-gray-700 hover:text-primary-700 px-3 py-1 rounded-full transition-colors"
                >
                  {suggestion}
                </button>
              )
            )}
          </div>
        )}
      </div> 
    </form>
  );
};

export default SearchBar;
