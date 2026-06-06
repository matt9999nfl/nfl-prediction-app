@echo off
gsutil setmeta -h "Cache-Control:no-cache, no-store, must-revalidate" gs://nfl-frontend-nfl-model-471509/index.html
gsutil setmeta -h "Cache-Control:public, max-age=31536000, immutable" gs://nfl-frontend-nfl-model-471509/assets/index-DSBzqtcP.js
gsutil setmeta -h "Cache-Control:public, max-age=31536000, immutable" gs://nfl-frontend-nfl-model-471509/assets/index-BZSIAztk.css
gsutil rm gs://nfl-frontend-nfl-model-471509/assets/index-B4VhH9iG.js
gsutil rm gs://nfl-frontend-nfl-model-471509/assets/index-sbG10bu5.css
echo DONE
