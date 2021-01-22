import time
from getpass import getpass

import pymongo

import scoresaber, beatsaver
import user
import config
from cr_formulas import *
from general import max_score

class HitbloqMongo():
    def __init__(self, password):
        self.client = pymongo.MongoClient('mongodb://dafluffypotato:' + password + '@dafluffypotato-db-shard-00-00-b1wgg.mongodb.net:27017,dafluffypotato-db-shard-00-01-b1wgg.mongodb.net:27017,dafluffypotato-db-shard-00-02-b1wgg.mongodb.net:27017/test?ssl=true&replicaSet=DaFluffyPotato-DB-shard-0&authSource=admin&retryWrites=true&w=majority', connectTimeoutMS=30000, socketTimeoutMS=None, connect=False, maxPoolsize=1)
        self.db = self.client['hitbloq_com']

    def gen_new_user_id(self):
        return self.db['counters'].find_and_modify(query={'type': 'user_id'}, update={'$inc': {'count': 1}})['count']

    def add_user(self, user):
        self.db['users'].insert_one(user.jsonify())

    def get_users(self, users):
        return [user.User().load(user_found) for user_found in self.db['users'].find({'_id': {'$in': users}})]

    def search_users(self, search):
        return [user.User().load(user_found) for user_found in self.db['users'].find(search)]

    def update_user(self, user, update=None):
        if update:
            self.db['users'].update_one({'_id': user.id}, update)
        else:
            self.db['users'].replace_one({'_id': user.id}, user.jsonify())

    def update_user_scores(self, user):
        scoresaber_api = scoresaber.ScoresaberInterface(self.db)
        new_scores = scoresaber_api.fetch_until(user.scoresaber_id, user.last_update)
        for i, score in enumerate(new_scores):
            print('adding score', i, '/', len(new_scores))
            self.add_score(user, score)
        self.update_user(user, {'$set': {'last_update': time.time()}})
        fresh_user = self.get_users([user.id])[0]
        self.update_user_cr_total(fresh_user)
        for map_pool_id in fresh_user.cr_totals:
            self.update_user_ranking(fresh_user, map_pool_id)

    def update_user_ranking(self, user, map_pool_id):
        if map_pool_id in user.cr_totals:
            resp = self.db['ladders'].update_one({'_id': map_pool_id, 'ladder.user': user.id}, {'$set': {'ladder.$.cr': user.cr_totals[map_pool_id]}})
            if not resp.matched_count:
                self.db['ladders'].update_one({'_id': map_pool_id}, {'$push': {'ladder': {'user': user.id, 'cr': user.cr_totals[map_pool_id]}}})
        self.sort_ladder(map_pool_id)

    def get_user_ranking(self, user, map_pool_id):
        # kinda yikes, but I'm not sure how to match just one field for indexOfArray
        if map_pool_id in user.cr_totals:
            resp = self.db['ladders'].aggregate([{'$match': {'_id': map_pool_id}}, {'$project': {'index': {'$indexOfArray': ['$ladder', {'user': user.id, 'cr': user.cr_totals[map_pool_id]}]}}}])
            return list(resp)[0]['index'] + 1
        else:
            return 0

    def get_ranking_slice(self, map_pool_id, start, end):
        return self.db['ladders'].find_one({'_id': map_pool_id}, {'ladder': {'$slice': [start, end]}})

    def sort_ladder(self, map_pool_id):
        self.db['ladders'].update_one({'_id': map_pool_id}, {'$push': {'ladder': {'$each': [], '$sort': {'cr': -1}}}})

    def format_score(self, user, scoresaber_json, leaderboard):
        score_data = {
            # typo in scoresaber api. lul
            'score': scoresaber_json['unmodififiedScore'],
            'time_set': scoresaber_json['epochTime'],
            'song_id': scoresaber_json['songHash'] + '|' + scoresaber_json['difficultyRaw'],
            'cr': calculate_cr(scoresaber_json['score'] / max_score(leaderboard['notes']) * 100, leaderboard['star_rating']),
            'user': user.id,
        }
        return score_data

    def delete_scores(self, leaderboard_id, score_id_list):
        self.db['scores'].delete_many({'_id': {'$in': score_id_list}})
        self.db['leaderboards'].update_one({'_id': leaderboard_id}, {'$pull': {'score_ids': {'$in': score_id_list}}})

    def fetch_scores(self, score_id_list):
        return self.db['scores'].find({'_id': {'$in': score_id_list}}).sort('time_set', -1)

    def replace_scores(self, scores):
        score_ids = [score['_id'] for score in scores]
        self.db['scores'].delete_many({'_id': {'$in': score_ids}})
        self.db['scores'].insert_many(scores)

    def update_user_score_order(self, user):
        user.load_scores(self)
        user.scores.sort(key=lambda x: x['cr'], reverse=True)
        print(user.scores)
        score_id_list = [score['_id'] for score in user.scores]
        self.db['users'].update_one({'_id': user.id}, {'$set': {'score_ids': score_id_list}})

    def update_user_cr_total(self, user):
        user.load_scores(self)
        user.scores.sort(key=lambda x: x['cr'], reverse=True)
        map_pool_ids = list(user.cr_totals)
        map_pools = self.search_ranked_lists({'_id': {'$in': map_pool_ids}})
        cr_counters = {map_pool_id : 0 for map_pool_id in map_pool_ids}
        cr_totals = {map_pool_id : 0 for map_pool_id in map_pool_ids}
        for score in user.scores:
            for map_pool in map_pools:
                if score['song_id'] in map_pool['leaderboard_id_list']:
                    cr_totals[map_pool['_id']] += cr_accumulation_curve(cr_counters[map_pool['_id']]) * score['cr']
                    cr_counters[map_pool['_id']] += 1
        for pool in cr_totals:
            user.cr_totals[pool] = cr_totals[pool]
        self.db['users'].update_one({'_id': user.id}, {'$set': {'total_cr': user.cr_totals}})

    def add_score(self, user, scoresaber_json):
        leaderboard_id = scoresaber_json['songHash'] + '|' + scoresaber_json['difficultyRaw']
        valid_leaderboard = True
        leaderboard = list(self.db['leaderboards'].find({'_id': leaderboard_id}))
        if len(leaderboard) == 0:
            leaderboard = self.create_leaderboard(leaderboard_id, scoresaber_json['songHash'])
            if not leaderboard:
                return False
        else:
            leaderboard = leaderboard[0]

        if valid_leaderboard:
            # delete old score data
            matching_scores = self.db['scores'].find({'user': user.id, 'song_id': scoresaber_json['songHash'] + '|' + scoresaber_json['difficultyRaw']})
            matching_scores = [score['_id'] for score in matching_scores]
            self.delete_scores(leaderboard_id, matching_scores)

            # add new score
            score_json = self.format_score(user, scoresaber_json, leaderboard)
            mongo_response = self.db['scores'].insert_one(score_json)
            inserted_id = mongo_response.inserted_id
            self.update_user(user, {'$push': {'score_ids': inserted_id}})
            self.db['leaderboards'].update_one({'_id': leaderboard_id}, {'$push': {'score_ids': inserted_id}})
            self.refresh_score_order(leaderboard_id)
            return True

    def refresh_score_order(self, leaderboard_id):
        leaderboard_data = self.db['leaderboards'].find_one({'_id': leaderboard_id})
        new_score_order = [score['_id'] for score in self.fetch_scores(leaderboard_data['score_ids']).sort('score', -1)]
        self.db['leaderboards'].update_one({'_id': leaderboard_id}, {'$set': {'score_ids': new_score_order}})

    def create_leaderboard(self, leaderboard_id, leaderboard_hash):
        print('Creating leaderboard:', leaderboard_id)

        # remove old instances
        self.db['leaderboards'].delete_many({'_id': leaderboard_id})

        leaderboard_difficulty = leaderboard_id.split('|')[-1]

        beatsaver_api = beatsaver.BeatSaverInterface()
        beatsaver_data = beatsaver_api.lookup_song_hash(leaderboard_hash)

        if beatsaver_data:
            characteristic = leaderboard_difficulty.split('_')[-1]
            try:
                characteristic = config.CHARACTERISTIC_CONVERSION[characteristic]
            except KeyError:
                print('ERROR:', characteristic, 'is not a known characteristic.')
                return False

            difficulty = leaderboard_difficulty.split('_')[1]
            difficulty = config.DIFFICULTY_CONVERSION[difficulty]

            # get the correct difficulty data based on characteristic and difficulty
            difficulty_data = [c['difficulties'] for c in beatsaver_data['metadata']['characteristics'] if c['name'] == characteristic][0][difficulty]
            if difficulty_data == None:
                print('ERROR: the', difficulty, 'difficulty may have been deleted from Beat Saver...')
                return False

            leaderboard_data = {
                '_id': leaderboard_id,
                'key': beatsaver_data['key'],
                'cover': beatsaver_data['coverURL'],
                'name': beatsaver_data['metadata']['songName'],
                'sub_name': beatsaver_data['metadata']['songSubName'],
                'artist': beatsaver_data['metadata']['songAuthorName'],
                'mapper': beatsaver_data['metadata']['levelAuthorName'],
                'bpm': beatsaver_data['metadata']['bpm'],
                'difficulty_settings': leaderboard_id.split('|')[-1],
                'difficulty': difficulty,
                'characteristic': characteristic,
                'duration': beatsaver_data['metadata']['duration'],
                'difficulty_duration': difficulty_data['duration'],
                'length': difficulty_data['length'],
                'njs': difficulty_data['njs'],
                'bombs': difficulty_data['bombs'],
                'notes': difficulty_data['notes'],
                'obstacles': difficulty_data['obstacles'],
                'hash': leaderboard_hash,
                'score_ids': [],
                'star_rating': 0.0,
            }

            self.db['leaderboards'].insert_one(leaderboard_data)

            return leaderboard_data

        else:
            print('ERROR:', leaderboard_hash, 'appears to have been deleted from Beat Saver.')
            return None

    def get_leaderboards(self, leaderboard_id_list):
        return list(self.db['leaderboards'].find({'_id': {'$in': leaderboard_id_list}}))

    def search_leaderboards(self, search):
        return list(self.db['leaderboards'].find(search))

    def update_leaderboard_data(self, leaderboard_id, updates):
        self.db['leaderboards'].update({'_id': leaderboard_id}, updates)

    def create_map_pool(self, name, cover='/static/default_pool_cover.png', third_party=False):
        self.db['ranked_lists'].insert_one({
            '_id': name,
            'leaderboard_id_list': [],
            'shown_name': name,
            'third_party': third_party,
            'cover': cover,
        })
        self.db['ladders'].insert_one({
            '_id': name,
            'ladder': [],
        })

    def rank_song(self, leaderboard_id, map_pool):
        self.db['ranked_lists'].update_one({'_id': map_pool}, {'$push': {'leaderboard_id_list': leaderboard_id}})

    def get_ranked_lists(self):
        return list(self.db['ranked_lists'].find({}))

    def search_ranked_lists(self, search):
        return list(self.db['ranked_lists'].find(search))

    def get_ranked_list(self, group_id):
        return self.db['ranked_lists'].find_one({'_id': group_id})

    def get_pool_ids(self, allow_third_party=True):
        if allow_third_party:
            return [v['_id'] for v in self.db['ranked_lists'].aggregate([{'$match': {'deletedAt': None}}, {'$group': {'_id': '$_id'}}])]
        else:
            return [v['_id'] for v in self.db['ranked_lists'].aggregate([{'$match': {'deletedAt': None, 'third_party': False}}, {'$group': {'_id': '$_id'}}])]

print('MongoDB requires a password!')
database = HitbloqMongo(getpass())
