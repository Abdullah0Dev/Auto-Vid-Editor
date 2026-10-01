https://www.pinterest.com/search/pins/?q=%D8%B9%D9%81%D9%88%20%D9%85%D8%B9%D9%86%20%D8%A8%D9%86%20%D8%B2%D8%A7%D8%A6%D8%AF%D8%A9%20%D8%B9%D9%86%20%D8%A7%D9%84%D8%A3%D8%B3%D8%B1%D9%89&rs=typed

go this url and give me the first 3 images direct URL path eg: https://i.pinimg.com/1200x/ba/5c/56/ba5c560b6d0654af1cfb63baafa5fc7d.jpg 


fbu run https://commons.wikimedia.org \                   ✔  Vid-Editor  
  --goal "Search Wikimedia Commons for Great Mosque of Damascus. Open the most relevant image. Then open the original full-resolution image itself and stop on the direct image URL. Do not download anything."


  fbu run https://www.pinterest.com/search/pins/?q=%D8%B9%D9%81%D9%88%20%D9%85%D8%B9%D9%86%20%D8%A8%D9%86%20%D8%B2%D8%A7%D8%A6%D8%AF%D8%A9%20%D8%B9%D9%86%20%D8%A7%D9%84%D8%A3%D8%B3%D8%B1%D9%89&rs=typed \
  --goal "go this url and give me the first 3 images direct URL path eg: https://i.pinimg.com/1200x/ba/5c/56/ba5c560b6d0654af1cfb63baafa5fc7d.jpg"
  

  mate I do have a vector searching with high quality assets.. which is a custom video full with b-roll I truned into reusable video to downlod.. and here is how I do search for a query:

python -c "

import sqlean as sqlite3

import sqlite_vec

from sentence_transformers import SentenceTransformer

from config import DB_PATH



model = SentenceTransformer('BAAI/bge-m3')

q = 'رجل يمشي في صحراء'

vec = model.encode(q, normalize_embeddings=True).astype('float32').tolist()



db = sqlite3.connect(DB_PATH)

db.enable_load_extension(True)

sqlite_vec.load(db)

db.enable_load_extension(False)



rows = db.execute(

    'SELECT c.source_id, c.path, c.caption_ar, '

    '       vec_distance_cosine(v.text_embedding, ?) AS d '

    'FROM clips_vec v JOIN clips c ON c.id = v.clip_id '

    'ORDER BY d LIMIT 5', (sqlite_vec.serialize_float32(vec),)

).fetchall()



for sid, path, cap, d in rows:

    print(f'{sid}  {d:.3f}  {cap}')

    print(f'      -> {path}')

"



so I do wanna add this into my logic.. as this above logic was another service i did so I do wanna include it in my main proect editor so how to go and apply it.. 