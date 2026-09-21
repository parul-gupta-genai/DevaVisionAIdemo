import { CloudSun, Wind, Droplets, Sun, ShieldCheck } from 'lucide-react'

export function WeatherWidget() {
  // Simulated construction site weather data with AI work recommendations
  const weather = {
    location: 'NCR Construction Site - Zone A',
    temp: '32°C',
    condition: 'Partly Cloudy',
    humidity: '58%',
    windSpeed: '12 km/h',
    uvIndex: 'Moderate (5)',
    aqi: '78 (Good)',
    craneSafety: 'SAFE',
    concretePouring: 'OPTIMAL',
  }

  return (
    <div className="glass-pro p-5 rounded-2xl flex flex-col justify-between relative overflow-hidden border border-foreground/10 hover:border-primary/30 transition-all duration-300">
      <div className="flex justify-between items-start">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <CloudSun className="w-5 h-5 text-warning animate-pulse" />
            <span className="text-xs font-bold tracking-widest uppercase text-muted-foreground">Site Micro-Climate</span>
          </div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-extrabold tracking-tight text-foreground">{weather.temp}</span>
            <span className="text-xs font-medium text-muted-foreground">{weather.condition}</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-success/15 border border-success/30 text-success text-xs font-semibold">
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Work Safe</span>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 my-3 py-2 border-y border-foreground/5 text-xs">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Wind className="w-3.5 h-3.5 text-info" />
          <span>Wind: <strong className="text-foreground font-semibold">{weather.windSpeed}</strong></span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Droplets className="w-3.5 h-3.5 text-primary" />
          <span>Hum: <strong className="text-foreground font-semibold">{weather.humidity}</strong></span>
        </div>
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Sun className="w-3.5 h-3.5 text-warning" />
          <span>AQI: <strong className="text-success font-semibold">{weather.aqi}</strong></span>
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] bg-foreground/5 px-3 py-2 rounded-xl border border-foreground/5">
        <span className="text-muted-foreground font-medium">Crane & Concrete Operations:</span>
        <span className="font-bold text-success flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-success"></span> Safe & Optimal
        </span>
      </div>
    </div>
  )
}
