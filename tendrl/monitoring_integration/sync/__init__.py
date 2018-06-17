import etcd
import json
import threading
import time

from tendrl.commons import sds_sync
from tendrl.commons.utils import etcd_utils
from tendrl.commons.utils import log_utils as logger
from tendrl.monitoring_integration.graphite import graphite_utils
from tendrl.monitoring_integration.graphite import GraphitePlugin
from tendrl.monitoring_integration.sync.dashbaord_sync import \
    SyncAlertDashboard
from tendrl.monitoring_integration.sync.gluster_cluster_details import \
    get_cluster_details


DEFAULT_SLEEP = 60


class MonitoringIntegrationSdsSyncThread(sds_sync.StateSyncThread):

    def __init__(self):
        super(MonitoringIntegrationSdsSyncThread, self).__init__()
        self._complete = threading.Event()
        self.plugin_obj = GraphitePlugin()
        self.sync_interval = None

    def run(self):
        aggregate_gluster_objects = NS.monitoring.definitions.\
            get_parsed_defs()["namespace.monitoring"]["graphite_data"]
        _sleep = 0
        prev_cluster_details = {}
        while not self._complete.is_set():
            if self.sync_interval is None:
                try:
                    config_data = json.loads(etcd_utils.read(
                        "_NS/gluster/config/data"
                    ).value)
                    try:
                        self.sync_interval = int(
                            config_data['data']['sync_interval']
                        )
                    except ValueError as ex:
                        logger.log(
                            "error",
                            NS.get("publisher_id", None),
                            {
                                'message': "Unable to parse tendrl-gluster-" +
                                "integration config 'sync_interval'"
                            }
                        )
                        raise ex
                except etcd.EtcdKeyNotFound as ex:
                    # Before cluster import sync_interval is not populated
                    time.sleep(DEFAULT_SLEEP)
                    continue
            if _sleep > 5:
                _sleep = self.sync_interval
            else:
                _sleep += 1
            try:
                all_cluster_details = get_cluster_details()
                cluster_details = self.plugin_obj.get_central_store_data(
                    aggregate_gluster_objects, all_cluster_details
                )
                graphite_utils.create_cluster_alias(all_cluster_details)
                metrics = graphite_utils.create_metrics(
                    aggregate_gluster_objects, cluster_details)
                metric_list = []
                for metric in metrics:
                    for key, value in metric.items():
                        if value:
                            metric_list.append("tendrl.%s %s %d" % (
                                key,
                                value,
                                int(time.time())
                            ))
                self.plugin_obj.push_metrics(metric_list)
                # Creating or refreshing alert dashboard
                if _sleep > 5:
                    prev_cluster_details = \
                        SyncAlertDashboard().refresh_dashboard(
                            all_cluster_details,
                            prev_cluster_details
                        )
                time.sleep(_sleep)
            except (etcd.EtcdKeyNotFound, AttributeError, KeyError) as ex:
                logger.log("error", NS.get("publisher_id", None),
                           {'message': str(ex)})
                time.sleep(_sleep)
