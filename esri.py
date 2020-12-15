from arcgis.gis import GIS
from arcgis.geocoding import geocode
import pickle
from pathlib2 import Path
import json
import pandas as pd
import requests
import json

class Arcgis():
    
    def __init__(self, config):
        self.config = self.rd_config(config)
        self.login = self.get_gis()
        
    @staticmethod
    def open_pick(p):
        '''Helper function to open pickle file if config file object pickled. Assumes path is
        a pathlib2 Path object.'''
        for val in ['.pickle', '.pkl']:
            if str(p).endswith(val) and p.exists():
                with open(p, 'rb') as f:
                    return pickle.load(f)
    @staticmethod  
    def rd_config(config):
        '''Reads in configuration object. Accounts for type of argument passed. Pattern Reference: Jwmazzi/usgpo'''
        try:
            return config if isinstance(config, dict) else json.load(open(config))
        except ValueError as ve:
            return Arcgis.rd_config(Arcgis.open_pick(config))
        except FileNotFoundError as e:
            print(f'Input not valid: {e}')
            sys.exit(1)
    
    def get_gis(self):
        login = GIS(
            self.config['esri_url'],
            self.config['username'],
            self.config['password']
        )
        return login
    
    def users(self):
        '''Returns all users within ArcGIS Online organization.'''
        return self.login.users.search()
    
    #Most code function below leaning on helper code found at (but I tightened up code):
    #https://community.esri.com/thread/212198-get-a-list-of-all-arcgis-items-with-arcgis-python-module
    #Got slightly different results with this function with arcgis 1.8 on personal machine. Version
    #here is 1.7.
    def get_items(self, user):
        '''Returns items from a specific user in a df.'''
        list_items = {v.itemid: v for (i, v) in enumerate(user.items())}
        #Will need to change this to be recursive to capture all folders in hierarchy. Unless captures all folders?
        for folder in user.folders:
            folder_items = user.items(folder = folder['title'])
            for item in folder_items:
                list_items[item.itemid] = item
        df = None
        if len(list_items) > 0:
            df = pd.DataFrame(list_items).transpose()#.reset_index()
            #df = df.drop('index', axis = 1)
        return df
    
    def all_content(self):
        '''Returns all content in ArcGIS org in a dataframe.'''
        #List comp faster than map.
        #Added sort = True to call to pd.concat() because will sort the columns (alpha). Will be auto in pd future.
        return pd.concat([self.get_items(u) for u in self.users()], axis = 0, sort = True)
    
    def get_all_items(self):
        result = [self.get_items(u) for u in self.users()]
        return pd.concat(result, axis = 0).reset_index()


class Address():
    #field_addresses = ['address', 'city', 'region', 'postal', 'country']
    
    def __init__(self, a):
        #An array or list of values for address entered in same order as list above..
        #self.arr = arr
        #Assumes address values entered in order of list above. If country not provided, not included.
        #self.multi_field_add = {Address.field_addresses[i]: self.arr[i] for (i, v) in enumerate(self.arr)}
        self.multi_field_add = a
        self.token = None
        
    def multi_field_geoc(self):
        '''Geocode request IF not planning to store an address in our systems.'''
        return geocode(self.multi_field_add)
    
    def find_best_add(self):
        '''Finds best address score in dict of dicts for multi field geocode with NO STORAGE.'''
        best = None
        to_use = None
        results = None
        if self.token:
            results = self.multi_field_geoc_storage(self.token)
        else:
            results = self.multi_field_geoc()
        if results:
            for r in results:
                score = r['score']
                if not best:
                    best = score
                    to_use = r
                else:
                    if score > best:
                        best = score
                        to_use = r
        return to_use['location'] if best else print(' '.join(test.multi_field_add.values()) + ' could not be found.')
    
    def long_lat(self):
        '''Returns long and lat from best scored address in geocode results for NO STORAGE.'''
        result = self.find_best_add()
        #Y is latitude. X is longitude.
        return result['x'], result['y']
    
    def multi_field_geoc_storage(self, token):
        '''#Used combo of these sites to complete:
        #https://developers.arcgis.com/rest/geocode/api-reference/geocoding-find-address-candidates.htm
        #https://developers.arcgis.com/rest/geocode/api-reference/geocoding-authenticate-a-request.htm'''
        self.token = token
        #Need to add http with "s" for security.
        beg_url = 'https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates?Address='
        #For requests need to use "%20" for spaces.
        add = self.multi_field_add['address'].replace(' ', '%20').lower()
        other = list({k: f'{k.title()}={v}' for (k, v) in self.multi_field_add.items() if k != 'address'}.values())
        to_join = [add] + other + [f'outFields=*', f'forStorage=true', f'token={token}', f'f=pjson']
        joined = '&'.join(to_join)
        return beg_url + joined
    
    def multi_field_geoc_request(self, token):
        url = self.multi_field_geoc_storage(token)
        geoc = requests.get(url).json()
        return geoc['candidates']

#Obtaining the token doesn't really need to be in the Address class.
def gis_token(ident, val):
    '''Returns token for application to make requests to geocoding service. Useful for when want to
    STORE the results of the geocode request. There is also an expires_in key (in addition to the
    access_token key) below that indicates how long a token is valid in seconds. May want to grab
    that later if needed.'''
    _id = f'''https://www.arcgis.com/sharing/oauth2/token?client_id={ident}'''
    sec = f'''&grant_type=client_credentials&client_secret={val}&f=pjson'''
    url = _id + sec
    geocode_json = requests.get(url).json()
    token = geocode_json['access_token']
    return token
