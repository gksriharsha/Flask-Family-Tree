from Tree import create_app

def post_request_cors(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,face-location,'
                                                         'Task-id,start_id,end_ids,Vertex-id-map')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
    return response

if __name__ == '__main__':
    app = create_app()
    app.after_request(post_request_cors)
    app.run()
