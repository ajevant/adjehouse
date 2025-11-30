import randomLocation from 'random-location';
import { Random } from 'random-js';
import { faker } from '@faker-js/faker';

const random = new Random();

// Country configurations with multiple cities for diversity
const COUNTRY_CONFIGS: any = {
  NED: {
    name: "Netherlands",
    phoneFormat: "mobile", // 06xxxxxxxx format
    countryCode: "NL",
    cities: [
      { name: "Amsterdam", state: "North Holland", coordinates: { latitude: 52.377956, longitude: 4.897070 } },
      { name: "Rotterdam", state: "South Holland", coordinates: { latitude: 51.9244, longitude: 4.4777 } },
      { name: "Utrecht", state: "Utrecht", coordinates: { latitude: 52.0907, longitude: 5.1214 } },
      { name: "The Hague", state: "South Holland", coordinates: { latitude: 52.0705, longitude: 4.3007 } }
    ]
  },
  USA: {
    name: "United States",
    phoneFormat: "us", // +1XXXXXXXXXX format
    countryCode: "US",
    cities: [
      // Major metro areas
      { name: "New York", state: "New York", coordinates: { latitude: 40.7128, longitude: -74.0060 } },
      { name: "Los Angeles", state: "California", coordinates: { latitude: 34.0522, longitude: -118.2437 } },
      { name: "Chicago", state: "Illinois", coordinates: { latitude: 41.8781, longitude: -87.6298 } },
      { name: "Houston", state: "Texas", coordinates: { latitude: 29.7604, longitude: -95.3698 } },
      { name: "Phoenix", state: "Arizona", coordinates: { latitude: 33.4484, longitude: -112.0740 } },
      { name: "Philadelphia", state: "Pennsylvania", coordinates: { latitude: 39.9526, longitude: -75.1652 } },
      { name: "San Antonio", state: "Texas", coordinates: { latitude: 29.4241, longitude: -98.4936 } },
      { name: "San Diego", state: "California", coordinates: { latitude: 32.7157, longitude: -117.1611 } },
      { name: "Dallas", state: "Texas", coordinates: { latitude: 32.7767, longitude: -96.7970 } },
      { name: "San Jose", state: "California", coordinates: { latitude: 37.3382, longitude: -121.8863 } },
      { name: "Austin", state: "Texas", coordinates: { latitude: 30.2672, longitude: -97.7431 } },
      { name: "Jacksonville", state: "Florida", coordinates: { latitude: 30.3322, longitude: -81.6557 } },
      { name: "Fort Worth", state: "Texas", coordinates: { latitude: 32.7555, longitude: -97.3308 } },
      { name: "Columbus", state: "Ohio", coordinates: { latitude: 39.9612, longitude: -82.9988 } },
      { name: "San Francisco", state: "California", coordinates: { latitude: 37.7749, longitude: -122.4194 } },
      { name: "Charlotte", state: "North Carolina", coordinates: { latitude: 35.2271, longitude: -80.8431 } },
      { name: "Indianapolis", state: "Indiana", coordinates: { latitude: 39.7684, longitude: -86.1581 } },
      { name: "Seattle", state: "Washington", coordinates: { latitude: 47.6062, longitude: -122.3321 } },
      { name: "Denver", state: "Colorado", coordinates: { latitude: 39.7392, longitude: -104.9903 } },
      { name: "Boston", state: "Massachusetts", coordinates: { latitude: 42.3601, longitude: -71.0589 } },
      { name: "Detroit", state: "Michigan", coordinates: { latitude: 42.3314, longitude: -83.0458 } },
      { name: "Nashville", state: "Tennessee", coordinates: { latitude: 36.1627, longitude: -86.7816 } },
      { name: "Portland", state: "Oregon", coordinates: { latitude: 45.5152, longitude: -122.6784 } },
      { name: "Las Vegas", state: "Nevada", coordinates: { latitude: 36.1699, longitude: -115.1398 } },
      { name: "Miami", state: "Florida", coordinates: { latitude: 25.7617, longitude: -80.1918 } },
      { name: "Atlanta", state: "Georgia", coordinates: { latitude: 33.7490, longitude: -84.3880 } },
      { name: "Oklahoma City", state: "Oklahoma", coordinates: { latitude: 35.4676, longitude: -97.5164 } },
      { name: "Raleigh", state: "North Carolina", coordinates: { latitude: 35.7796, longitude: -78.6382 } },
      { name: "Omaha", state: "Nebraska", coordinates: { latitude: 41.2565, longitude: -95.9345 } },
      { name: "Minneapolis", state: "Minnesota", coordinates: { latitude: 44.9778, longitude: -93.2650 } },
      { name: "Tulsa", state: "Oklahoma", coordinates: { latitude: 36.1540, longitude: -95.9928 } },
      { name: "Cleveland", state: "Ohio", coordinates: { latitude: 41.4993, longitude: -81.6944 } },
      { name: "Wichita", state: "Kansas", coordinates: { latitude: 37.6872, longitude: -97.3301 } },
      { name: "Arlington", state: "Texas", coordinates: { latitude: 32.7357, longitude: -97.1081 } },
      { name: "Tampa", state: "Florida", coordinates: { latitude: 27.9506, longitude: -82.4572 } },
      { name: "New Orleans", state: "Louisiana", coordinates: { latitude: 29.9511, longitude: -90.0715 } },
      { name: "Bakersfield", state: "California", coordinates: { latitude: 35.3733, longitude: -119.0187 } },
      { name: "Aurora", state: "Colorado", coordinates: { latitude: 39.7294, longitude: -104.8319 } },
      { name: "Anaheim", state: "California", coordinates: { latitude: 33.8366, longitude: -117.9143 } },
      { name: "Honolulu", state: "Hawaii", coordinates: { latitude: 21.3099, longitude: -157.8581 } },
      { name: "Santa Ana", state: "California", coordinates: { latitude: 33.7455, longitude: -117.8677 } },
      { name: "Riverside", state: "California", coordinates: { latitude: 33.9533, longitude: -117.3962 } },
      { name: "Corpus Christi", state: "Texas", coordinates: { latitude: 27.8006, longitude: -97.3964 } },
      { name: "Lexington", state: "Kentucky", coordinates: { latitude: 38.0406, longitude: -84.5037 } },
      { name: "Henderson", state: "Nevada", coordinates: { latitude: 36.0395, longitude: -114.9817 } },
      { name: "Stockton", state: "California", coordinates: { latitude: 37.9577, longitude: -121.2908 } },
      { name: "Saint Paul", state: "Minnesota", coordinates: { latitude: 44.9537, longitude: -93.0900 } },
      { name: "Cincinnati", state: "Ohio", coordinates: { latitude: 39.1031, longitude: -84.5120 } },
      { name: "St. Louis", state: "Missouri", coordinates: { latitude: 38.6270, longitude: -90.1994 } },
      { name: "Pittsburgh", state: "Pennsylvania", coordinates: { latitude: 40.4406, longitude: -79.9959 } },
      { name: "Greensboro", state: "North Carolina", coordinates: { latitude: 36.0726, longitude: -79.7920 } },
      { name: "Anchorage", state: "Alaska", coordinates: { latitude: 61.2181, longitude: -149.9003 } },
      { name: "Plano", state: "Texas", coordinates: { latitude: 33.0198, longitude: -96.6989 } },
      { name: "Lincoln", state: "Nebraska", coordinates: { latitude: 40.8136, longitude: -96.7026 } },
      { name: "Orlando", state: "Florida", coordinates: { latitude: 28.5383, longitude: -81.3792 } },
      { name: "Irvine", state: "California", coordinates: { latitude: 33.6846, longitude: -117.8265 } },
      { name: "Newark", state: "New Jersey", coordinates: { latitude: 40.7357, longitude: -74.1724 } },
      { name: "Durham", state: "North Carolina", coordinates: { latitude: 35.9940, longitude: -78.8986 } },
      { name: "Chula Vista", state: "California", coordinates: { latitude: 32.6401, longitude: -117.0842 } },
      { name: "Toledo", state: "Ohio", coordinates: { latitude: 41.6528, longitude: -83.5379 } },
      { name: "Fort Wayne", state: "Indiana", coordinates: { latitude: 41.0793, longitude: -85.1394 } },
      { name: "St. Petersburg", state: "Florida", coordinates: { latitude: 27.7676, longitude: -82.6403 } },
      { name: "Laredo", state: "Texas", coordinates: { latitude: 27.5306, longitude: -99.4803 } },
      { name: "Jersey City", state: "New Jersey", coordinates: { latitude: 40.7178, longitude: -74.0431 } },
      { name: "Chandler", state: "Arizona", coordinates: { latitude: 33.3062, longitude: -111.8413 } },
      { name: "Madison", state: "Wisconsin", coordinates: { latitude: 43.0731, longitude: -89.4012 } },
      { name: "Lubbock", state: "Texas", coordinates: { latitude: 33.5779, longitude: -101.8552 } },
      { name: "Scottsdale", state: "Arizona", coordinates: { latitude: 33.4942, longitude: -111.9261 } },
      { name: "Reno", state: "Nevada", coordinates: { latitude: 39.5296, longitude: -119.8138 } },
      { name: "Buffalo", state: "New York", coordinates: { latitude: 42.8864, longitude: -78.8784 } },
      { name: "Gilbert", state: "Arizona", coordinates: { latitude: 33.3528, longitude: -111.7890 } },
      { name: "Glendale", state: "Arizona", coordinates: { latitude: 33.5387, longitude: -112.1860 } },
      { name: "North Las Vegas", state: "Nevada", coordinates: { latitude: 36.1989, longitude: -115.1175 } },
      { name: "Winston-Salem", state: "North Carolina", coordinates: { latitude: 36.0999, longitude: -80.2442 } },
      { name: "Chesapeake", state: "Virginia", coordinates: { latitude: 36.7682, longitude: -76.2875 } },
      { name: "Norfolk", state: "Virginia", coordinates: { latitude: 36.8508, longitude: -76.2859 } },
      { name: "Fremont", state: "California", coordinates: { latitude: 37.5485, longitude: -121.9886 } },
      { name: "Garland", state: "Texas", coordinates: { latitude: 32.9126, longitude: -96.6389 } },
      { name: "Irving", state: "Texas", coordinates: { latitude: 32.8140, longitude: -96.9489 } },
      { name: "Hialeah", state: "Florida", coordinates: { latitude: 25.8576, longitude: -80.2781 } },
      { name: "Richmond", state: "Virginia", coordinates: { latitude: 37.5407, longitude: -77.4360 } },
      { name: "Boise", state: "Idaho", coordinates: { latitude: 43.6150, longitude: -116.2023 } },
      { name: "Spokane", state: "Washington", coordinates: { latitude: 47.6588, longitude: -117.4260 } },
      { name: "Baton Rouge", state: "Louisiana", coordinates: { latitude: 30.4515, longitude: -91.1871 } },
      { name: "Tacoma", state: "Washington", coordinates: { latitude: 47.2529, longitude: -122.4443 } },
      { name: "San Bernardino", state: "California", coordinates: { latitude: 34.1083, longitude: -117.2898 } },
      { name: "Modesto", state: "California", coordinates: { latitude: 37.6391, longitude: -120.9969 } },
      { name: "Fontana", state: "California", coordinates: { latitude: 34.0922, longitude: -117.4350 } },
      { name: "Des Moines", state: "Iowa", coordinates: { latitude: 41.6005, longitude: -93.6091 } },
      { name: "Moreno Valley", state: "California", coordinates: { latitude: 33.9425, longitude: -117.2297 } },
      { name: "Santa Clarita", state: "California", coordinates: { latitude: 34.3917, longitude: -118.5426 } },
      { name: "Fayetteville", state: "North Carolina", coordinates: { latitude: 35.0527, longitude: -78.8784 } },
      { name: "Birmingham", state: "Alabama", coordinates: { latitude: 33.5186, longitude: -86.8104 } },
      { name: "Oxnard", state: "California", coordinates: { latitude: 34.1975, longitude: -119.1771 } },
      { name: "Rochester", state: "New York", coordinates: { latitude: 43.1566, longitude: -77.6088 } },
      { name: "Port St. Lucie", state: "Florida", coordinates: { latitude: 27.2730, longitude: -80.3582 } },
      { name: "Grand Rapids", state: "Michigan", coordinates: { latitude: 42.9634, longitude: -85.6681 } },
      { name: "Huntsville", state: "Alabama", coordinates: { latitude: 34.7304, longitude: -86.5861 } },
      { name: "Salt Lake City", state: "Utah", coordinates: { latitude: 40.7608, longitude: -111.8910 } },
      { name: "Frisco", state: "Texas", coordinates: { latitude: 33.1507, longitude: -96.8236 } },
      { name: "Yonkers", state: "New York", coordinates: { latitude: 40.9312, longitude: -73.8987 } },
      { name: "Amarillo", state: "Texas", coordinates: { latitude: 35.2220, longitude: -101.8313 } },
      { name: "Glendale", state: "California", coordinates: { latitude: 34.1425, longitude: -118.2551 } },
      { name: "Huntington Beach", state: "California", coordinates: { latitude: 33.6603, longitude: -117.9992 } },
      { name: "Grand Prairie", state: "Texas", coordinates: { latitude: 32.7459, longitude: -96.9978 } },
      { name: "Brownsville", state: "Texas", coordinates: { latitude: 25.9017, longitude: -97.4975 } },
      { name: "McKinney", state: "Texas", coordinates: { latitude: 33.1972, longitude: -96.6397 } },
      { name: "Montgomery", state: "Alabama", coordinates: { latitude: 32.3668, longitude: -86.2999 } },
      { name: "Akron", state: "Ohio", coordinates: { latitude: 41.0814, longitude: -81.5190 } },
      { name: "Little Rock", state: "Arkansas", coordinates: { latitude: 34.7465, longitude: -92.2896 } },
      { name: "Augusta", state: "Georgia", coordinates: { latitude: 33.4735, longitude: -82.0105 } },
      { name: "Mobile", state: "Alabama", coordinates: { latitude: 30.6954, longitude: -88.0399 } },
      { name: "Shreveport", state: "Louisiana", coordinates: { latitude: 32.5252, longitude: -93.7502 } },
      { name: "Chattanooga", state: "Tennessee", coordinates: { latitude: 35.0456, longitude: -85.3097 } },
      { name: "Vancouver", state: "Washington", coordinates: { latitude: 45.6387, longitude: -122.6615 } },
      { name: "Knoxville", state: "Tennessee", coordinates: { latitude: 35.9606, longitude: -83.9207 } },
      { name: "Worcester", state: "Massachusetts", coordinates: { latitude: 42.2626, longitude: -71.8023 } },
      { name: "Providence", state: "Rhode Island", coordinates: { latitude: 41.8240, longitude: -71.4128 } },
      { name: "Newport News", state: "Virginia", coordinates: { latitude: 37.0871, longitude: -76.4730 } },
      { name: "Santa Rosa", state: "California", coordinates: { latitude: 38.4404, longitude: -122.7141 } },
      { name: "Oceanside", state: "California", coordinates: { latitude: 33.1959, longitude: -117.3795 } },
      { name: "Salem", state: "Oregon", coordinates: { latitude: 44.9429, longitude: -123.0351 } },
      { name: "Elk Grove", state: "California", coordinates: { latitude: 38.4088, longitude: -121.3716 } },
      { name: "Garden Grove", state: "California", coordinates: { latitude: 33.7747, longitude: -117.9414 } },
      { name: "Pembroke Pines", state: "Florida", coordinates: { latitude: 26.0076, longitude: -80.2962 } },
      { name: "Peoria", state: "Arizona", coordinates: { latitude: 33.5806, longitude: -112.2374 } },
      { name: "Eugene", state: "Oregon", coordinates: { latitude: 44.0521, longitude: -123.0868 } },
      { name: "Cary", state: "North Carolina", coordinates: { latitude: 35.7915, longitude: -78.7811 } },
      { name: "Springfield", state: "Missouri", coordinates: { latitude: 37.2090, longitude: -93.2923 } },
      { name: "Fort Lauderdale", state: "Florida", coordinates: { latitude: 26.1224, longitude: -80.1373 } },
      { name: "Corona", state: "California", coordinates: { latitude: 33.8753, longitude: -117.5664 } },
      { name: "Lancaster", state: "California", coordinates: { latitude: 34.6868, longitude: -118.1542 } },
      { name: "Hayward", state: "California", coordinates: { latitude: 37.6688, longitude: -122.0808 } },
      { name: "Palmdale", state: "California", coordinates: { latitude: 34.5794, longitude: -118.1165 } },
      { name: "Salinas", state: "California", coordinates: { latitude: 36.6777, longitude: -121.6555 } },
      { name: "Paterson", state: "New Jersey", coordinates: { latitude: 40.9168, longitude: -74.1718 } },
      { name: "Joliet", state: "Illinois", coordinates: { latitude: 41.5250, longitude: -88.0817 } },
      { name: "Bellevue", state: "Washington", coordinates: { latitude: 47.6101, longitude: -122.2015 } },
      { name: "Macon", state: "Georgia", coordinates: { latitude: 32.8407, longitude: -83.6324 } },
      { name: "Dayton", state: "Ohio", coordinates: { latitude: 39.7589, longitude: -84.1916 } },
      { name: "Savannah", state: "Georgia", coordinates: { latitude: 32.0809, longitude: -81.0912 } },
      { name: "Clarksville", state: "Tennessee", coordinates: { latitude: 36.5298, longitude: -87.3595 } },
      { name: "Mesquite", state: "Texas", coordinates: { latitude: 32.7668, longitude: -96.5992 } },
      { name: "Syracuse", state: "New York", coordinates: { latitude: 43.0481, longitude: -76.1474 } },
      { name: "Kansas City", state: "Kansas", coordinates: { latitude: 39.1142, longitude: -94.6275 } },
      { name: "Hollywood", state: "Florida", coordinates: { latitude: 26.0112, longitude: -80.1495 } },
      { name: "Torrance", state: "California", coordinates: { latitude: 33.8358, longitude: -118.3406 } },
      { name: "Escondido", state: "California", coordinates: { latitude: 33.1192, longitude: -117.0864 } },
      { name: "Naperville", state: "Illinois", coordinates: { latitude: 41.7508, longitude: -88.1535 } },
      { name: "Pasadena", state: "Texas", coordinates: { latitude: 29.6911, longitude: -95.2091 } },
      { name: "Sunnyvale", state: "California", coordinates: { latitude: 37.3688, longitude: -122.0363 } },
      { name: "Alexandria", state: "Virginia", coordinates: { latitude: 38.8048, longitude: -77.0469 } },
      { name: "Rockford", state: "Illinois", coordinates: { latitude: 42.2711, longitude: -89.0940 } },
      { name: "Pomona", state: "California", coordinates: { latitude: 34.0551, longitude: -117.7499 } },
      { name: "Pasadena", state: "California", coordinates: { latitude: 34.1478, longitude: -118.1445 } }
    ]
  },
  MEX: {
    name: "Mexico",
    phoneFormat: "mexico", // +52 format
    countryCode: "MX",
    cities: [
      { name: "Mexico City", state: "Mexico City", coordinates: { latitude: 19.432608, longitude: -99.133208 } },
      { name: "Guadalajara", state: "Jalisco", coordinates: { latitude: 20.6597, longitude: -103.3496 } },
      { name: "Monterrey", state: "Nuevo León", coordinates: { latitude: 25.6866, longitude: -100.3161 } },
      { name: "Puebla", state: "Puebla", coordinates: { latitude: 19.0414, longitude: -98.2063 } },
      { name: "Tijuana", state: "Baja California", coordinates: { latitude: 32.5149, longitude: -117.0382 } },
      { name: "León", state: "Guanajuato", coordinates: { latitude: 21.1224, longitude: -101.6860 } },
      { name: "Juárez", state: "Chihuahua", coordinates: { latitude: 31.6904, longitude: -106.4245 } },
      { name: "Zapopan", state: "Jalisco", coordinates: { latitude: 20.7214, longitude: -103.3918 } },
      { name: "Mérida", state: "Yucatán", coordinates: { latitude: 20.9674, longitude: -89.5926 } },
      { name: "San Luis Potosí", state: "San Luis Potosí", coordinates: { latitude: 22.1565, longitude: -100.9855 } },
      { name: "Aguascalientes", state: "Aguascalientes", coordinates: { latitude: 21.8853, longitude: -102.2916 } },
      { name: "Hermosillo", state: "Sonora", coordinates: { latitude: 29.0729, longitude: -110.9559 } },
      { name: "Saltillo", state: "Coahuila", coordinates: { latitude: 25.4232, longitude: -100.9945 } },
      { name: "Mexicali", state: "Baja California", coordinates: { latitude: 32.6245, longitude: -115.4523 } },
      { name: "Culiacán", state: "Sinaloa", coordinates: { latitude: 24.8091, longitude: -107.3940 } },
      { name: "Querétaro", state: "Querétaro", coordinates: { latitude: 20.5888, longitude: -100.3899 } },
      { name: "Chihuahua", state: "Chihuahua", coordinates: { latitude: 28.6353, longitude: -106.0889 } },
      { name: "Morelia", state: "Michoacán", coordinates: { latitude: 19.7060, longitude: -101.1949 } },
      { name: "Torreón", state: "Coahuila", coordinates: { latitude: 25.5428, longitude: -103.4068 } },
      { name: "Acapulco", state: "Guerrero", coordinates: { latitude: 16.8531, longitude: -99.8237 } },
      { name: "Cancún", state: "Quintana Roo", coordinates: { latitude: 21.1619, longitude: -86.8515 } },
      { name: "Toluca", state: "México", coordinates: { latitude: 19.2827, longitude: -99.6557 } },
      { name: "Reynosa", state: "Tamaulipas", coordinates: { latitude: 26.0922, longitude: -98.2777 } },
      { name: "Tuxtla Gutiérrez", state: "Chiapas", coordinates: { latitude: 16.7516, longitude: -93.1029 } },
      { name: "Veracruz", state: "Veracruz", coordinates: { latitude: 19.1738, longitude: -96.1342 } },
      { name: "Mazatlán", state: "Sinaloa", coordinates: { latitude: 23.2494, longitude: -106.4111 } },
      { name: "Tlalnepantla", state: "México", coordinates: { latitude: 19.5287, longitude: -99.1959 } },
      { name: "Xalapa", state: "Veracruz", coordinates: { latitude: 19.5436, longitude: -96.9102 } },
      { name: "Irapuato", state: "Guanajuato", coordinates: { latitude: 20.6767, longitude: -101.3542 } },
      { name: "Celaya", state: "Guanajuato", coordinates: { latitude: 20.5289, longitude: -100.8157 } },
      { name: "Durango", state: "Durango", coordinates: { latitude: 24.0277, longitude: -104.6532 } },
      { name: "Victoria", state: "Tamaulipas", coordinates: { latitude: 23.7369, longitude: -99.1411 } },
      { name: "Tepic", state: "Nayarit", coordinates: { latitude: 21.5041, longitude: -104.8915 } },
      { name: "Campeche", state: "Campeche", coordinates: { latitude: 19.8301, longitude: -90.5349 } },
      { name: "Cuernavaca", state: "Morelos", coordinates: { latitude: 18.9211, longitude: -99.2372 } },
      { name: "Oaxaca", state: "Oaxaca", coordinates: { latitude: 17.0732, longitude: -96.7266 } },
      { name: "Tampico", state: "Tamaulipas", coordinates: { latitude: 22.2331, longitude: -97.8611 } },
      { name: "Ensenada", state: "Baja California", coordinates: { latitude: 31.8667, longitude: -116.5969 } },
      { name: "Puerto Vallarta", state: "Jalisco", coordinates: { latitude: 20.6534, longitude: -105.2253 } },
      { name: "Nuevo Laredo", state: "Tamaulipas", coordinates: { latitude: 27.4769, longitude: -99.5155 } },
      { name: "Uruapan", state: "Michoacán", coordinates: { latitude: 19.4211, longitude: -102.0633 } },
      { name: "Los Mochis", state: "Sinaloa", coordinates: { latitude: 25.7933, longitude: -108.9856 } },
      { name: "Guanajuato", state: "Guanajuato", coordinates: { latitude: 21.0190, longitude: -101.2574 } },
      { name: "Pachuca", state: "Hidalgo", coordinates: { latitude: 20.1011, longitude: -98.7591 } },
      { name: "Zacatecas", state: "Zacatecas", coordinates: { latitude: 22.7709, longitude: -102.5832 } },
      { name: "Tlaxcala", state: "Tlaxcala", coordinates: { latitude: 19.3139, longitude: -98.2404 } },
      { name: "Colima", state: "Colima", coordinates: { latitude: 19.2452, longitude: -103.7241 } },
      { name: "Villahermosa", state: "Tabasco", coordinates: { latitude: 17.9892, longitude: -92.9475 } },
      { name: "Matamoros", state: "Tamaulipas", coordinates: { latitude: 25.8796, longitude: -97.5048 } },
      { name: "La Paz", state: "Baja California Sur", coordinates: { latitude: 24.1426, longitude: -110.3128 } }
    ]
  },
  MAR: {
    name: "Morocco",
    phoneFormat: "morocco", // +212 6XXXXXXXX or +212 7XXXXXXXX format
    countryCode: "MA",
    cities: [
      { name: "Casablanca", state: "Casablanca-Settat", coordinates: { latitude: 33.5731, longitude: -7.5898 } },
      { name: "Rabat", state: "Rabat-Salé-Kénitra", coordinates: { latitude: 34.0209, longitude: -6.8416 } },
      { name: "Marrakech", state: "Marrakesh-Safi", coordinates: { latitude: 31.6295, longitude: -7.9811 } }
    ]
  },
  DZA: {
    name: "Algeria",
    phoneFormat: "algeria", // +213 5XXXXXXXX, +213 6XXXXXXXX, or +213 7XXXXXXXX format
    countryCode: "DZ",
    cities: [
      { name: "Algiers", state: "Algiers", coordinates: { latitude: 36.7538, longitude: 3.0588 } },
      { name: "Oran", state: "Oran", coordinates: { latitude: 35.6969, longitude: -0.6331 } },
      { name: "Constantine", state: "Constantine", coordinates: { latitude: 36.3650, longitude: 6.6147 } }
    ]
  }
};

// Valid US area codes by state
const VALID_US_AREA_CODES: { [key: string]: string[] } = {
  'California': [
    '209', '213', '310', '323', '408', '415', '510', '530', '559', '562',
    '619', '626', '628', '650', '657', '661', '669', '707', '714', '747',
    '760', '805', '818', '831', '858', '909', '916', '925', '949', '951'
  ],
  'Texas': [
    '210', '214', '254', '281', '325', '361', '409', '430', '432', '469',
    '512', '682', '713', '724', '737', '806', '817', '830', '832', '903', '915', '940', '956', '972', '979'
  ],
  'Florida': [
    '239', '305', '321', '352', '386', '407', '561', '727', '754', '772', '786', '813', '850', '863', '904', '941', '954'
  ],
  'New York': [
    '212', '315', '347', '516', '518', '585', '607', '631', '646', '716', '718', '845', '914', '917', '929'
  ],
  'Illinois': [
    '217', '224', '309', '312', '331', '618', '630', '708', '773', '779', '815', '847', '872'
  ]
};

// Phone number generators for each country
function generatePhoneNumber(countryCode: string): string {
  switch (countryCode) {
    case 'NED':
      // Dutch mobile format: 06xxxxxxxx (8 digits after 06)
      return `06${faker.number.int({ min: 10000000, max: 99999999 })}`;
    
    case 'USA':
      // US format: +1 (XXX) XXX-XXXX with valid area codes
      const config = COUNTRY_CONFIGS[countryCode];
      let areaCodes: string[] = [];
      
      // Get valid area codes for the state
      if (config.state && VALID_US_AREA_CODES[config.state]) {
        areaCodes = VALID_US_AREA_CODES[config.state];
      } else {
        // Fallback: use all California area codes
        areaCodes = VALID_US_AREA_CODES['California'];
      }
      
      const areaCode = faker.helpers.arrayElement(areaCodes);
      const exchange = faker.number.int({ min: 200, max: 999 }); // Exchange codes can't start with 0 or 1
      const lineNumber = faker.number.int({ min: 1000, max: 9999 });
      return `+1${areaCode}${exchange}${lineNumber}`;
    
    case 'MEX':
      // Mexican format: +52 XX XXXX XXXX
      const areaCodeMex = faker.number.int({ min: 10, max: 99 });
      const prefixMex = faker.number.int({ min: 1000, max: 9999 });
      const lineNumberMex = faker.number.int({ min: 1000, max: 9999 });
      return `+52 ${areaCodeMex} ${prefixMex} ${lineNumberMex}`;
    
    case 'MAR':
      // Moroccan mobile format: +212 6XXXXXXXX or +212 7XXXXXXXX (8 digits after prefix)
      const mobilePrefix = faker.helpers.arrayElement(['6', '7']);
      const mobileNumber = faker.number.int({ min: 10000000, max: 99999999 });
      return `+212 ${mobilePrefix}${mobileNumber}`;
    
    case 'DZA':
      // Algerian mobile format: +213 5XXXXXXXX, +213 6XXXXXXXX, or +213 7XXXXXXXX (8 digits after prefix)
      const mobilePrefixAlg = faker.helpers.arrayElement(['5', '6', '7']);
      const mobileNumberAlg = faker.number.int({ min: 10000000, max: 99999999 });
      return `+213 ${mobilePrefixAlg}${mobileNumberAlg}`;
    
    default:
      return faker.phone.number();
  }
}

// Generate a single address for the specified country
async function generateAddress(countryCode: string, radius: number = 5000, retryCount: number = 0): Promise<any> {
  const config = COUNTRY_CONFIGS[countryCode];
  if (!config) {
    throw new Error(`Unsupported country code: ${countryCode}. Supported: NED, USA, MEX, MAR, DZA`);
  }

  const MAPBOX_ACCESS_TOKEN = 'pk.eyJ1IjoicmVtb2xvIiwiYSI6ImNtZnlmZWExMzBkZjgya3M0NWhwN29zZGIifQ.OtGBtuszBKU3nvyOWhq6Gg'

  try {
    // Randomly select a city from the country's cities array
    const randomCity = config.cities[Math.floor(Math.random() * config.cities.length)];
    
    // Generate random point within radius of selected city center (max 5km for better address coverage)
    const pointInCircle = randomLocation.randomCirclePoint(randomCity.coordinates, radius);
    
    // Reverse geocode using Mapbox API
    const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${pointInCircle.longitude},${pointInCircle.latitude}.json?access_token=${MAPBOX_ACCESS_TOKEN}&country=${config.countryCode}&types=address,poi&limit=1`;
    
    const response = await fetch(url);
    const data = await response.json();
    
    // Check if response is valid
    if (!data || !data.features || data.features.length === 0) {
      throw new Error('Invalid geocoding response');
    }
    
    const feature = data.features[0];
    
    // Extract address components from Mapbox response
    const addressComponents: any = {};
    if (feature.context) {
      feature.context.forEach((component: any) => {
        if (component.id.startsWith('postcode')) {
          addressComponents.postcode = component.text;
        } else if (component.id.startsWith('place')) {
          addressComponents.city = component.text;
        } else if (component.id.startsWith('region')) {
          addressComponents.state = component.text;
        } else if (component.id.startsWith('country')) {
          addressComponents.country = component.text;
        }
      });
    }

    // Extract street information from place_name or address
    let streetAndNumber = '';
    if (feature.properties && feature.properties.address) {
      streetAndNumber = `${feature.properties.address} ${feature.text || 'Street'}`;
    } else if (feature.place_name) {
      // Extract street from place_name (first part before comma)
      const parts = feature.place_name.split(',');
      streetAndNumber = parts[0].trim() || `${faker.number.int({ min: 1, max: 999 })} ${faker.location.street()}`;
    } else {
      // Fallback to generated street
      streetAndNumber = `${faker.number.int({ min: 1, max: 999 })} ${faker.location.street()}`;
    }

    // More lenient address validation - only retry once to reduce error spam
    if (!streetAndNumber || streetAndNumber.trim() === '') {
      if (retryCount < 3) {
        console.log(`Retrying address generation (attempt ${retryCount + 1}/3)`);
        return generateAddress(countryCode, radius, retryCount + 1);
      }
      // Fallback to basic address if geocoding fails
      return generateFallbackAddress(countryCode);
    }

    // Generate person data using faker v9 syntax
    const firstName = faker.person.firstName();
    const lastName = faker.person.lastName();
    const phoneNumber = generatePhoneNumber(countryCode);

    return {
      FIRST_NAME: firstName,
      LAST_NAME: lastName,
      STREET_AND_NUMBER: streetAndNumber,
      POSTALCODE: addressComponents.postcode || faker.location.zipCode(),
      CITY: addressComponents.city || randomCity.name,
      STATE: addressComponents.state || randomCity.state,
      PHONE_NUMBER: phoneNumber
    };

  } catch (error: any) {
    console.error('Error in generateAddress:', error.message);
    // Silently retry once, then fall back to synthetic address generation
    // With 5km radius, we hit fewer empty areas but still need fallback for parks/water
    
    if (retryCount < 3) {
      console.log(`Retrying address generation (attempt ${retryCount + 1}/3)`);
      return generateAddress(countryCode, radius, retryCount + 1);
    }
    
    // Fallback to basic address generation
    return generateFallbackAddress(countryCode);
  }
}

// Fallback address generation when geocoding fails
function generateFallbackAddress(countryCode: string): any {
  const config = COUNTRY_CONFIGS[countryCode];
  const randomCity = config.cities[Math.floor(Math.random() * config.cities.length)];
  const firstName = faker.person.firstName();
  const lastName = faker.person.lastName();
  const phoneNumber = generatePhoneNumber(countryCode);
  
  // Generate random street number and name
  const streetNumber = faker.number.int({ min: 1, max: 999 });
  const streetName = faker.location.street();
  
  return {
    FIRST_NAME: firstName,
    LAST_NAME: lastName,
    STREET_AND_NUMBER: `${streetNumber} ${streetName}`,
    POSTALCODE: faker.location.zipCode(),
    CITY: randomCity.name,
    STATE: randomCity.state,
    PHONE_NUMBER: phoneNumber
  };
}

// Generate multiple addresses
async function generateAddresses(countryCode: string, count: number = 1, radius: number = 5000): Promise<any[]> {
  const addresses: any[] = [];
  
  for (let i = 0; i < count; i++) {
    try {
      const address = await generateAddress(countryCode, radius);
      addresses.push(address);
    } catch (error: any) {
      console.error(`Error generating address ${i + 1}:`, error.message);
      // Continue with next address
    }
  }
  
  return addresses;
}

export { generateAddress, generateAddresses, COUNTRY_CONFIGS, generatePhoneNumber };