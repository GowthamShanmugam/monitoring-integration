from etcd import EtcdKeyNotFound
from subprocess import CalledProcessError
from tendrl.commons.event import Event
from tendrl.commons.message import ExceptionMessage
from tendrl.monitoring_integration.alert import constants
from tendrl.monitoring_integration.alert.handlers import AlertHandler
from tendrl.monitoring_integration.alert import utils
from tendrl.monitoring_integration.alert.exceptions import NodeNotFound


class ClusterHandler(AlertHandler):

    handles = 'cluster'
    representive_name = 'cluster_alert'

    def __init__(self):
        AlertHandler.__init__(self)

    def format_alert(self, alert_json):
        alert  = self.parse_alert_metrics(alert_json)
        try:
            alert["alert_id"] = None
            alert["node_id"] = constants.NOT_AVAILABLE 
            alert["time_stamp"] = alert_json['NewStateDate']
            alert["resource"] = self.representive_name
            alert['alert_type'] = constants.ALERT_TYPE 
            alert['severity'] = constants.TENDRL_GRAFANA_SEVERITY_MAP[
                alert_json['State']]
            alert['significance'] = constants.SIGNIFICANCE_HIGH
            alert['pid'] = utils.find_grafana_pid()
            alert['source'] = constants.ALERT_SOURCE
            alert['tags']['alert_catagory'] = constants.CLUSTER
            if alert['severity'] == "WARNING":
                alert['tags']['message'] = ("Cluster utilization of cluster %s is" \
                " %s which is above the %s threshold (%s)." % (
                    alert['tags']['cluster_id'],
                    alert['current_value'],
                    alert['severity'],
                    alert['tags']['warning_max']
                ))
            elif alert['severity'] == "INFO":
                alert['tags']['message'] = ("Cluster utilization of cluster %s is"\
                " back to normal" % (
                    alert['tags']['cluster_id']
                ))
            elif  alert['severity'] == "UNKNOWN":
                alert['tags']['message'] = ("Cluster utilization of cluster %s "\
                "contains no data, unable to find state" % (
                    alert['tags']['cluster']
                ))
            return alert
        except (KeyError,
                CalledProcessError,
                EtcdKeyNotFound,
                NodeNotFound) as ex:
            Event(
                ExceptionMessage(
                    "error",
                    NS.publisher_id, 
                    {
                        "message": "Error in converting grafana"
                        "alert into tendrl alert %s" % alert_json,
                        "exception": ex
                    }
                )
            )
    
    def parse_alert_metrics(self, alert_json):
        alert = {}
        alert['tags'] = {}
        alert['current_value'] = utils.find_current_value(
            alert_json['EvalData'])
        target = utils.find_alert_target(
            alert_json['Settings']['conditions'])
        alert['tags']['warning_max'] = utils.find_warning_max(
            alert_json['Settings']['conditions'][0]['evaluator']['params'])
        # identifying cluster_id and node_id from any one
        # alert metric (all have same)
        metric = target.split(",")[0].split(".")
        for i in range(0, len(metric)):
            if  metric[i] == "clusters":
                alert['tags']['cluster_id'] = metric[i + 1]
        return alert
