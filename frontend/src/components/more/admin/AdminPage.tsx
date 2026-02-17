import DbInfo from "./DbInfo";
import CacheControls from "./CacheControls";
import ChannelDigest from "./ChannelDigest";

export default function AdminPage() {
  return (
    <div className="admin-page">
      <DbInfo />
      <CacheControls />
      <ChannelDigest />
    </div>
  );
}
