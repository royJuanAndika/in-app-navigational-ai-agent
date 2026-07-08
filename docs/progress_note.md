11 april 2026 starbucks manyar with lady

aku findout deepseek r1 70b nya nggak bisa karena vram usage nya 199 gb, sedangkan vram nya gpu3 cuma 120 gb an. i decided pake gemma4 31b. claude bilang cukup bagus, asal pake chunking.

akhirnya aku buat script untuk ngelakuin ini di ```/prompting_chunk```. dichunk dulu, lalu untuk setiap chunk diprompt. lalu json nya dilengkapin untuk setiap chunk. every inference takes kira kira ~80s. 

jangan lupa pake --backend remote kalau jalanin di laptop.

terakhir buat fitur streaming progress.

jalanin dry run untuk liat promptnya

aku nemuin dia elements nya jadinya kayak flat gitu. langsung page->element. nggak page->element->element. 

### !! findout apakah ini perlu diresolve

aku juga udah buat script untuk validate id nya dengan generate js. scriptnya di ```/validate```. nanti keluar hasilnya, hasilnya di copas ke console dev tools nya webnya. jangan lupa, abis dirun, harus jalanin function lagi.

### !! buat workflow untuk ngilangin element yang unnecessary. lalu untuk nambahin juga yang hilang.

### !! juga findout apakah untuk setiap iterasi per chunk, bisakah iterasi yang sekarang ini bisa lihat hasil yang sebelumnya. atau lihat hasil json sebelumnya kayak apa. ini mungkin necessary karena hasil yang sekarang tergantung sama hasil yang sebelumnya.

jangan lupa ini bisa dijalanin di gpu3, biar laptopku ga harus nyala terus.