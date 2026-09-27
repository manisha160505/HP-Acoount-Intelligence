// Creates the application's database user on the first start of an empty
// MongoDB data directory (docker-entrypoint-initdb.d). Later starts skip it.
//
// The backend connects as this user, not as root: readWrite on the one
// application database covers everything it does - reads, writes, index
// creation, and the per-workspace collections LightRAG creates and drops.
//
//   MONGODB_URI=mongodb://<MONGO_APP_USER>:<MONGO_APP_PASSWORD>@mongodb:27017/<DB_NAME>?authSource=<DB_NAME>

const appDb = process.env.MONGO_APP_DB;
const user = process.env.MONGO_APP_USER;
const password = process.env.MONGO_APP_PASSWORD;

if (!appDb || !user || !password) {
  throw new Error("MONGO_APP_DB, MONGO_APP_USER and MONGO_APP_PASSWORD must be set");
}

db.getSiblingDB(appDb).createUser({
  user: user,
  pwd: password,
  roles: [{ role: "readWrite", db: appDb }],
});

print(`created user ${user} with readWrite on ${appDb}`);
