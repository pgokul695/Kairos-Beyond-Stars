import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const ComparisonChart = ({ data, showRecharts = false }) => {
  const categories = [
    { key: 'ambiance', label: 'Ambiance', icon: '🏛️' },
    { key: 'service', label: 'Service', icon: '👨‍🍳' },
    { key: 'food', label: 'Food Quality', icon: '🍽️' },
    { key: 'value', label: 'Value', icon: '💰' },
    { key: 'location', label: 'Location', icon: '📍' }
  ];

  const getBarColor = (score) => {
    if (score >= 95) return '#10b981';
    if (score >= 90) return '#3b82f6';
    if (score >= 85) return '#f59e0b';
    return '#ef4444';
  };

  const getGradientClass = (score) => {
    if (score >= 95) return 'from-green-500 to-emerald-500';
    if (score >= 90) return 'from-blue-500 to-cyan-500';
    if (score >= 85) return 'from-yellow-500 to-orange-500';
    return 'from-orange-500 to-red-500';
  };

  // Prepare data for recharts
  const chartData = categories.map(cat => ({
    name: cat.label,
    score: data[cat.key],
    icon: cat.icon
  }));

  const CustomTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-white px-4 py-2 rounded-lg shadow-xl border border-gray-200">
          <p className="font-semibold text-gray-900">{payload[0].payload.name}</p>
          <p className="text-sm text-gray-600">{payload[0].value}%</p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="bg-white rounded-2xl p-6 shadow-lg">
      <div className="flex items-center space-x-3 mb-6">
        <div className="bg-gradient-to-br from-primary-500 to-yellow-500 p-2 rounded-lg">
          <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <div>
          <h3 className="text-xl font-bold text-gray-900">AI Analysis</h3>
          <p className="text-sm text-gray-500">Breakdown by category</p>
        </div>
      </div>

      {showRecharts ? (
        <div className="h-64 mb-6">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis 
                dataKey="name" 
                tick={{ fontSize: 12, fill: '#666' }}
                tickFormatter={(value) => value.split(' ')[0]}
              />
              <YAxis tick={{ fontSize: 12, fill: '#666' }} domain={[0, 100]} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="score" radius={[8, 8, 0, 0]}>
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getBarColor(entry.score)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="space-y-5">
          {categories.map((category) => {
            const score = data[category.key];
            return (
              <div key={category.key} className="group">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <span className="text-lg">{category.icon}</span>
                    <span className="text-sm font-semibold text-gray-700">
                      {category.label}
                    </span>
                  </div>
                  <span className="text-sm font-bold text-gray-900">{score}%</span>
                </div>
                
                <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className={`absolute inset-y-0 left-0 bg-gradient-to-r ${getGradientClass(score)} rounded-full transition-all duration-1000 ease-out group-hover:shadow-lg`}
                    style={{ width: `${score}%` }}
                  >
                    <div className="absolute inset-0 bg-white/20 animate-pulse"></div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Overall Score */}
      <div className="mt-6 pt-6 border-t border-gray-200">
        <div className="flex items-center justify-between">
          <span className="text-base font-bold text-gray-900">Overall Score</span>
          <div className="flex items-center space-x-2">
            <div className="text-3xl font-bold bg-gradient-to-r from-primary-600 to-yellow-600 bg-clip-text text-transparent">
              {Math.round(
                Object.values(data).reduce((a, b) => a + b, 0) / Object.values(data).length
              )}%
            </div>
            <div className="bg-gradient-to-br from-primary-500 to-yellow-500 p-2 rounded-lg">
              <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
              </svg>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ComparisonChart;
