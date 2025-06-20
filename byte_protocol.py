MSG_TYPE_SERVICE_REQUEST,MSG_TYPE_TAXI_UPDATE,MSG_TYPE_TAXI_ORDER,MSG_TYPE_CUSTOMER_NOTIFICATION=1,2,4,5
STATUS_KO,STATUS_OK,STATUS_FINALIZADO,STATUS_IDLE=0,1,2,3
STATUS_GOING_TO_PICKUP,STATUS_GOING_TO_DROPOFF,STOPPED_SENSOR,STOPPED_BY_CENTRAL,STATUS_UNAVAILABLE=4,5,6,7,8
STATUS_ARRIVED_PICKUP,STATUS_SENSOR_FAIL,STATUS_TAXI_LOST=9,10,11
CMD_GOTO,CMD_PARAR,CMD_REANUDAR,CMD_DESTINO,CMD_VOLVERABASE=0,1,2,3,4
def encode_service_request(c,p,d)->bytes:return bytes([MSG_TYPE_SERVICE_REQUEST,c,p[0],p[1],ord(d)])
def encode_taxi_payload(t,p,s)->bytes:return bytes([int(t),p[0],p[1],s])
def decode_taxi_payload(p:bytes)->tuple:return p[0],(p[1],p[2]),p[3]
def encode_taxi_order(c,d=(0,0))->bytes:return bytes([MSG_TYPE_TAXI_ORDER,c,d[0],d[1]])
def encode_customer_notification(s,t=0,p=(0,0))->bytes:
    if s==STATUS_OK:return bytes([MSG_TYPE_CUSTOMER_NOTIFICATION,s,t,0])
    if s==STATUS_FINALIZADO:return bytes([MSG_TYPE_CUSTOMER_NOTIFICATION,s,p[0],p[1]])
    return bytes([MSG_TYPE_CUSTOMER_NOTIFICATION,s,0,0])